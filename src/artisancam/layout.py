"""Place lines of text on the stock: font units -> millimetres.

Output frame ("stock frame"): origin at the top-left corner of the stock, x grows to the
right, y grows DOWNWARD, in millimetres. Converting to the machine's axes is gcode.py's job.

There are two lines: "top" (anchored to the top edge) and "bottom" (anchored to the bottom
edge). Each is centred across the stock, kept inside the edge margin, and kept clear of the
keep-out zones from the config.
"""

from __future__ import annotations

import math

from .config import KeepOut, Settings
from .font import Font, Point, Stroke

_LABELS = {"top": "Top text", "bottom": "Bottom text"}


class LayoutError(ValueError):
    """The text cannot be engraved as requested; the message is meant for the user."""


def _describe(chars: list[str]) -> str:
    return ", ".join(repr(c) for c in chars)


def layout_text(text: str, font: Font, settings: Settings, line: str = "top") -> list[Stroke]:
    """Place one line of text. `line` is "top" or "bottom"; errors name the line."""
    if line not in _LABELS:
        raise ValueError(f"line must be 'top' or 'bottom', got {line!r}")
    try:
        return _layout(text, font, settings, line)
    except LayoutError as exc:
        raise LayoutError(f"{_LABELS[line]}: {exc}") from None


def layout_lines(top: str, bottom: str, font: Font, settings: Settings) -> list[Stroke]:
    """Place the top and/or the bottom line; a blank line is simply left out."""
    placed: dict[str, list[Stroke]] = {}
    for line, text in (("top", top), ("bottom", bottom)):
        if text.strip():
            placed[line] = layout_text(text, font, settings, line)
    if not placed:
        raise LayoutError("Nothing to engrave: enter a top text, a bottom text, or both.")
    if len(placed) == 2:
        top_end = max(y for stroke in placed["top"] for _, y in stroke)
        bottom_start = min(y for stroke in placed["bottom"] for _, y in stroke)
        if bottom_start - top_end < settings.edge_margin:
            raise LayoutError(
                f"The top and bottom text are too close together: {bottom_start - top_end:.2f} mm apart, "
                f"at least {settings.edge_margin:g} mm are needed."
            )
    return [stroke for line in ("top", "bottom") for stroke in placed.get(line, [])]


def _layout(text: str, font: Font, settings: Settings, line: str) -> list[Stroke]:
    if "\n" in text or "\r" in text:
        raise LayoutError("Only a single line of text is supported.")
    missing = font.missing(text)
    if missing:
        raise LayoutError(f"The font has no glyph for: {_describe(missing)}")

    if line == "top":
        height, cap_top = settings.top_height, settings.top_margin
    else:
        height = settings.bottom_height
        cap_top = settings.stock_length - settings.bottom_margin - height  # baseline sits bottom_margin above the edge

    # Proportional spacing: a constant gap between the ink of neighbouring letters (so a narrow
    # "I" does not leave a hole), plus an extra space_width for every space character.
    scale = height / font.cap_height
    strokes: list[Stroke] = []
    ink_end: float | None = None  # x of the right edge of the previous letter, font units
    extra = 0.0
    for char in text:
        glyph = font.glyphs[char]
        if not glyph:  # a space: no ink, only width
            extra += settings.space_width
            continue
        xs = [x for stroke in glyph for x, _ in stroke]
        origin = -min(xs) if ink_end is None else ink_end + settings.letter_gap + extra - min(xs)
        ink_end, extra = origin + max(xs), 0.0
        for glyph_stroke in glyph:
            strokes.append([((origin + x) * scale, cap_top + (font.cap_height - y) * scale) for x, y in glyph_stroke])
    if not strokes:
        raise LayoutError("Nothing to engrave: enter at least one visible character.")

    # Centre the ink (not the character cells) across the stock width.
    xs = [x for stroke in strokes for x, _ in stroke]
    shift = settings.stock_width / 2 - (min(xs) + max(xs)) / 2
    strokes = [[(x + shift, y) for x, y in stroke] for stroke in strokes]

    _check_fits(strokes, settings)
    _check_keepouts(strokes, settings)
    return strokes


def _check_fits(strokes: list[Stroke], s: Settings) -> None:
    xs = [x for stroke in strokes for x, _ in stroke]
    ys = [y for stroke in strokes for _, y in stroke]
    m = s.edge_margin
    problems = []
    if min(xs) < m or max(xs) > s.stock_width - m:
        width = max(xs) - min(xs)
        problems.append(f"too wide: the text is {width:.2f} mm wide, {s.stock_width - 2 * m:.2f} mm are available")
    if min(ys) < m or max(ys) > s.stock_length - m:
        problems.append(
            f"too low or too high: the text spans {min(ys):.2f} to {max(ys):.2f} mm from the top edge, "
            f"allowed is {m:.2f} to {s.stock_length - m:.2f} mm"
        )
    if problems:
        raise LayoutError("The text does not fit on the stock: " + "; ".join(problems) + ".")


def _check_keepouts(strokes: list[Stroke], s: Settings) -> None:
    for zone in s.keepouts:
        if _touches(strokes, zone, s.keepout_clearance):
            raise LayoutError(
                f"The text comes too close to the keep-out zone '{zone.name}' "
                f"(it must stay {s.keepout_clearance:g} mm away). Shorten the text or move it."
            )


def _touches(strokes: list[Stroke], zone: KeepOut, clearance: float) -> bool:
    """True if any engraved segment is closer than `clearance` to the zone (rectangles are grown square)."""
    if zone.shape == "circle":
        centre, limit = (zone.x, zone.y), zone.diameter / 2 + clearance
        return any(_point_segment_distance(centre, a, b) < limit for stroke in strokes for a, b in zip(stroke, stroke[1:]))
    box = (zone.x - clearance, zone.y - clearance, zone.x + zone.width + clearance, zone.y + zone.height + clearance)
    return any(_segment_hits_box(a, b, box) for stroke in strokes for a, b in zip(stroke, stroke[1:]))


def _point_segment_distance(p: Point, a: Point, b: Point) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length2 = dx * dx + dy * dy
    t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length2))
    return math.dist(p, (a[0] + t * dx, a[1] + t * dy))


def _segment_hits_box(a: Point, b: Point, box: tuple[float, float, float, float]) -> bool:
    """Liang-Barsky clipping: does the segment a-b touch or enter the axis-aligned box?"""
    x0, y0, x1, y1 = box
    dx, dy = b[0] - a[0], b[1] - a[1]
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, a[0] - x0), (dx, x1 - a[0]), (-dy, a[1] - y0), (dy, y1 - a[1])):
        if p == 0:
            if q < 0:
                return False  # parallel to this edge and outside it
        else:
            t = q / p
            if p < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
            if t0 > t1:
                return False
    return True
