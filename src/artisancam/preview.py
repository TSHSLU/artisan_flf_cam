"""Read finished G-code text back into a list of moves, for the preview.

The preview draws what the machine will actually run, so it parses the G-code string instead
of reusing the generator's internal data: a bug in gcode.py (mirrored axis, wrong Z) shows up
in the picture. No Qt in here. Coordinates stay in machine axes (X right, Y <= 0 below the
origin, Z = 0 at the stock top); flipping Y for the screen is the view's job.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

_WORD = re.compile(r"([A-Z])(-?\d+(?:\.\d+)?)")


@dataclass(frozen=True)
class Move:
    """One straight XY move. `cutting` means the tool is below the stock surface the whole way."""

    start: tuple[float, float]
    end: tuple[float, float]
    cutting: bool

    @property
    def length(self) -> float:
        return math.dist(self.start, self.end)


@dataclass(frozen=True)
class ParsedProgram:
    moves: tuple[Move, ...]
    strokes: int  # number of plunges into the material

    @property
    def cut_moves(self) -> tuple[Move, ...]:
        return tuple(m for m in self.moves if m.cutting)

    @property
    def cut_length(self) -> float:
        return sum(m.length for m in self.moves if m.cutting)


def parse_gcode(text: str) -> ParsedProgram:
    """Parse G0/G1 moves. Comments, other commands and moves without XY travel (plunge, lift) add no
    segment; a plunge from above the stock to below it is counted as one stroke."""
    x = y = 0.0  # the machine is assumed to start at the origin
    z: float | None = None
    moves: list[Move] = []
    strokes = 0
    for raw in text.splitlines():
        words = _WORD.findall(raw.split(";")[0])
        if not words or words[0][0] != "G" or int(float(words[0][1])) not in (0, 1):
            continue
        args = {letter: float(value) for letter, value in words[1:]}
        nx, ny, nz = args.get("X", x), args.get("Y", y), args.get("Z", z)
        if nz is not None and z is not None and z >= 0 > nz:
            strokes += 1
        if (nx, ny) != (x, y):
            below = nz is not None and nz < 0 and z is not None and z < 0
            moves.append(Move((x, y), (nx, ny), cutting=below and int(float(words[0][1])) == 1))
        x, y, z = nx, ny, nz
    return ParsedProgram(tuple(moves), strokes)
