"""Read the bundled single-line SVG font into strokes.

This is the only module that knows the font file format. A glyph is a tuple of strokes and a
stroke is a list of (x, y) points in font units (y up, baseline at 0, capital height =
Font.cap_height). Arcs are flattened to straight segments here because the machine only
does G0/G1 moves.
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from functools import cache
from pathlib import Path

Point = tuple[float, float]
Stroke = list[Point]

FONT_PATH = Path(__file__).resolve().parent / "fonts" / "ISO3098-Regular.svg"

_SVG_NS = "{http://www.w3.org/2000/svg}"
_TOKEN = re.compile(r"[MLA]|-?\d+(?:\.\d+)?")
_MAX_ARC_STEP = math.radians(10)  # sagitta stays below ~0.0025 mm at 3.5 mm capital height
_JOIN_TOLERANCE = 1e-6


class FontError(ValueError):
    """The font file cannot be read or contains something this reader does not support."""


@dataclass(frozen=True)
class Font:
    glyphs: dict[str, tuple[Stroke, ...]]
    cap_height: float

    def missing(self, text: str) -> list[str]:
        """Characters of `text` that have no glyph, without duplicates, in order of appearance."""
        return list(dict.fromkeys(ch for ch in text if ch not in self.glyphs))


def arc_points(start: Point, radius: float, large: bool, sweep: bool, end: Point) -> list[Point]:
    """Flatten a circular SVG arc (no rotation) into points after `start`, ending exactly at `end`.

    Follows the SVG endpoint-to-centre conversion. `sweep` means increasing angle in the
    coordinate system as given, which for this y-up font is counter-clockwise.
    """
    (x1, y1), (x2, y2) = start, end
    if (x1, y1) == (x2, y2):
        return []
    hx, hy = (x1 - x2) / 2, (y1 - y2) / 2
    d2 = hx * hx + hy * hy
    r = max(radius, math.sqrt(d2))  # radius too small for the chord: SVG says scale it up
    coef = math.sqrt(max(0.0, (r * r - d2) / d2))
    sign = -1.0 if large == sweep else 1.0
    cx = sign * coef * hy + (x1 + x2) / 2
    cy = -sign * coef * hx + (y1 + y2) / 2
    a1 = math.atan2(y1 - cy, x1 - cx)
    a2 = math.atan2(y2 - cy, x2 - cx)
    delta = a2 - a1
    if sweep and delta < 0:
        delta += 2 * math.pi
    elif not sweep and delta > 0:
        delta -= 2 * math.pi
    steps = max(1, math.ceil(abs(delta) / _MAX_ARC_STEP))
    points = [(cx + r * math.cos(a1 + delta * i / steps), cy + r * math.sin(a1 + delta * i / steps)) for i in range(1, steps)]
    points.append(end)
    return points


def _segments(path: str, glyph: str) -> list[list[Point]]:
    """Parse one `d` attribute into separate sub-paths (every M starts a new one)."""
    tokens = _TOKEN.findall(path)
    pos = 0
    subpaths: list[list[Point]] = []

    def numbers(count: int) -> list[float]:
        nonlocal pos
        chunk = tokens[pos : pos + count]
        if len(chunk) != count or any(t in "MLA" for t in chunk):
            raise FontError(f"Glyph {glyph!r}: malformed path data")
        pos += count
        return [float(t) for t in chunk]

    def point() -> Point:
        x, y = numbers(2)
        return (x, y)

    while pos < len(tokens):
        command = tokens[pos]
        pos += 1
        if command == "M":
            subpaths.append([point()])
        elif not subpaths:
            raise FontError(f"Glyph {glyph!r}: path does not start with M")
        elif command == "L":
            subpaths[-1].append(point())
        elif command == "A":
            rx, ry, rotation, large, sweep, x, y = numbers(7)
            if rx != ry or rotation != 0:
                raise FontError(f"Glyph {glyph!r}: only circular arcs without rotation are supported")
            subpaths[-1].extend(arc_points(subpaths[-1][-1], rx, bool(large), bool(sweep), (x, y)))
        else:
            raise FontError(f"Glyph {glyph!r}: unsupported path command {command!r}")
    return subpaths


def _join(subpaths: list[list[Point]]) -> list[Stroke]:
    """Merge consecutive sub-paths that end where the next one starts, so a letter like D is one cut."""
    strokes: list[Stroke] = []
    for sub in subpaths:
        if strokes and math.dist(strokes[-1][-1], sub[0]) < _JOIN_TOLERANCE:
            strokes[-1].extend(sub[1:])
        else:
            strokes.append(list(sub))
    return strokes


def parse_font(svg_text: str) -> Font:
    try:
        root = ET.fromstring(svg_text)
    except ET.ParseError as exc:
        raise FontError(f"Font file is not valid XML: {exc}") from None
    face = root.find(f".//{_SVG_NS}font-face")
    if face is None or "cap-height" not in face.attrib:
        raise FontError("Font file has no <font-face cap-height=...>")
    glyphs: dict[str, tuple[Stroke, ...]] = {}
    for node in root.iter(f"{_SVG_NS}glyph"):
        char = node.get("unicode")
        if char is None or len(char) != 1:
            continue  # ligatures and glyphs without a character are not needed
        glyphs[char] = tuple(_join(_segments(node.get("d", ""), char)))
    return Font(glyphs=glyphs, cap_height=float(face.attrib["cap-height"]))


@cache
def load_default_font() -> Font:
    return parse_font(FONT_PATH.read_text(encoding="utf-8"))
