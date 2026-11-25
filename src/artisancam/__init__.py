"""ArtisanCAM: minimal text-to-G-code engraver for the Snapmaker Artisan."""

from __future__ import annotations

from collections.abc import Sequence

from .config import Settings
from .fixture import shift, slot_offsets
from .font import Font, Stroke, load_default_font
from .gcode import generate_gcode
from .layout import LayoutError, layout_lines
from .toolpath import build_toolpath


def create_program(top: str, settings: Settings, *, bottom: str = "", font: Font | None = None) -> str:
    """One cover at the origin: text -> strokes -> placed strokes -> cuts -> G-code text.

    `top` is engraved near the top edge, `bottom` (optional) near the bottom edge; either may be
    left blank. The [fixture] settings are ignored here. Raises LayoutError with a user-facing
    message if the text cannot be engraved.
    """
    font = font or load_default_font()
    strokes = layout_lines(top, bottom, font, settings)
    label = " / ".join(text.strip() for text in (top, bottom) if text.strip())
    return generate_gcode(build_toolpath(strokes), settings, label=label)


def _blank(text: str) -> bool:
    return not text.strip()


def create_program_for_slots(
    slots: Sequence[tuple[str, str]], settings: Settings, *, font: Font | None = None
) -> str:
    """Several covers in one program: `slots` holds one (top, bottom) text pair per fixture slot.

    Each cover is laid out exactly as a single cover, then moved into its slot. Slots with no
    text are skipped. With a one-slot fixture the result is identical to create_program().
    Errors name the slot, e.g. "Slot 4: Bottom text: ...".
    """
    offsets = slot_offsets(settings)
    if len(slots) > len(offsets):
        raise ValueError(f"{len(slots)} slot texts given, but the fixture has only {len(offsets)} slots")
    if len(offsets) == 1:
        top, bottom = slots[0] if slots else ("", "")
        return create_program(top, settings, bottom=bottom, font=font)

    font = font or load_default_font()
    strokes: list[Stroke] = []
    labels: list[str] = []
    for number, ((top, bottom), (dx, dy)) in enumerate(zip(slots, offsets), 1):
        if _blank(top) and _blank(bottom):
            continue
        try:
            placed = layout_lines(top, bottom, font, settings)
        except LayoutError as exc:
            raise LayoutError(f"Slot {number}: {exc}") from None
        strokes += shift(placed, dx, dy)
        labels.append(f"Slot {number}: " + " / ".join(t.strip() for t in (top, bottom) if t.strip()))
    if not strokes:
        raise LayoutError("Nothing to engrave: enter a text for at least one slot.")
    return generate_gcode(build_toolpath(strokes), settings, slot_labels=labels)
