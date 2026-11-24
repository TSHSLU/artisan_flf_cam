"""Turn placed strokes into the ordered list of cuts the machine will make.

v0 keeps the font's natural order. This module is the one place where a smarter order
(shortest travel) or other strategies would go later, so layout and G-code never change.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .font import Point, Stroke

_SAME_POINT = 1e-6  # mm


@dataclass(frozen=True)
class Cut:
    """One continuous engraving pass at constant depth: plunge at points[0], trace, lift at points[-1]."""

    points: tuple[Point, ...]


def build_toolpath(strokes: list[Stroke]) -> list[Cut]:
    cuts = []
    for stroke in strokes:
        points: list[Point] = []
        for p in stroke:
            if not points or math.dist(points[-1], p) > _SAME_POINT:
                points.append(p)
        if len(points) >= 2:  # a stroke without length would only plunge and lift
            cuts.append(Cut(tuple(points)))
    return cuts
