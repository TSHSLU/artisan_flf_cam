"""ArtisanCAM: minimal text-to-G-code engraver for the Snapmaker Artisan."""

from __future__ import annotations

from .config import Settings
from .font import Font, load_default_font
from .gcode import generate_gcode
from .layout import layout_lines
from .toolpath import build_toolpath


def create_program(top: str, settings: Settings, *, bottom: str = "", font: Font | None = None) -> str:
    """The whole pipeline: text -> strokes -> placed strokes -> cuts -> G-code text.

    `top` is engraved near the top edge, `bottom` (optional) near the bottom edge; either may be
    left blank. Raises LayoutError with a user-facing message if the text cannot be engraved.
    """
    font = font or load_default_font()
    strokes = layout_lines(top, bottom, font, settings)
    label = " / ".join(text.strip() for text in (top, bottom) if text.strip())
    return generate_gcode(build_toolpath(strokes), settings, label=label)
