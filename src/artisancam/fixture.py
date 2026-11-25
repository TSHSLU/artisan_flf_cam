"""Where the slots of a multi-cover fixture are, and moving a cover's strokes into its slot.

Slots form a grid of [fixture] columns x rows, numbered row by row from the top-left slot:

    slot 1   slot 2   slot 3        X0 Y0 is the top-left corner of slot 1
    slot 4   slot 5   slot 6

Offsets are in the stock frame (millimetres, x right, y DOWN), like everything before gcode.py.
No Qt in here.
"""

from __future__ import annotations

from .config import Settings
from .font import Stroke


def slot_offsets(settings: Settings) -> list[tuple[float, float]]:
    """(dx, dy) of each slot's top-left corner relative to slot 1, in slot order."""
    return [
        (column * settings.pitch_x, row * settings.pitch_y)
        for row in range(settings.rows)
        for column in range(settings.columns)
    ]


def fixture_size(settings: Settings) -> tuple[float, float]:
    """Width and length of the area covered by all slots, from slot 1's corner to the far corner."""
    return (
        (settings.columns - 1) * settings.pitch_x + settings.stock_width,
        (settings.rows - 1) * settings.pitch_y + settings.stock_length,
    )


def shift(strokes: list[Stroke], dx: float, dy: float) -> list[Stroke]:
    """The same strokes moved by (dx, dy)."""
    return [[(x + dx, y + dy) for x, y in stroke] for stroke in strokes]
