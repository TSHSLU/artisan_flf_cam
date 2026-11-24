"""ArtisanCAM: minimal text-to-G-code engraver for the Snapmaker Artisan."""

from __future__ import annotations

from .config import Settings
from .font import Font, load_default_font
from .gcode import generate_gcode
from .layout import layout_text
from .toolpath import build_toolpath


def create_program(text: str, settings: Settings, font: Font | None = None) -> str:
    """The whole pipeline: text -> strokes -> placed strokes -> cuts -> G-code text.

    Raises LayoutError with a user-facing message if the text cannot be engraved.
    """
    font = font or load_default_font()
    strokes = layout_text(text, font, settings)
    return generate_gcode(build_toolpath(strokes), settings, label=text)
