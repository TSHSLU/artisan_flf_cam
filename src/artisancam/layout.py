"""Place lines of text on the stock: font units -> millimetres.

Output frame ("stock frame"): origin at the top-left corner of the stock, x grows to the
right, y grows DOWNWARD, in millimetres. Converting to the machine's axes is gcode.py's job.

There are two lines: "top" (anchored to the top edge) and "bottom" (anchored to the bottom
edge). Each is centred across the stock and kept inside the edge margin.
"""

from __future__ import annotations

from .config import Settings
from .font import Font, Stroke

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
