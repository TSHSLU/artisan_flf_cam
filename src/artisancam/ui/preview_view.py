"""2D preview of the finished G-code, seen from above.

It parses the G-code text (see preview.py) and draws it on a QGraphicsScene whose units are
millimetres and whose origin is the stock's top-left corner, x right and y DOWN, the same frame
the keep-out zones use. Machine Y is negative below the origin, so the scene uses y = -Y.
Mouse wheel zooms, dragging pans, a double click fits the stock to the view again.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsScene, QGraphicsView

from ..config import Settings
from ..preview import ParsedProgram, parse_gcode

CUT_COLOR = QColor("#0b8a4a")
TRAVEL_COLOR = QColor("#9aa4ad")
ZONE_COLOR = QColor("#d64545")
ORIGIN_COLOR = QColor("#d64545")
START_COLOR = QColor("#2563eb")
_PADDING = 3.0  # mm of empty space around the stock in the view
_STALE_OPACITY = 0.25


def _pen(color: QColor, width: float, dashed: bool = False) -> QPen:
    pen = QPen(color, width)
    pen.setCosmetic(True)  # constant width in pixels, whatever the zoom
    if dashed:
        pen.setStyle(Qt.PenStyle.DashLine)
    return pen


class PreviewView(QGraphicsView):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QBrush(QColor("#eef1f4")))
        self.setMinimumSize(220, 320)
        self._auto_fit = True
        self._program_items: list[QGraphicsItem] = []
        self._drawn_cut_moves = 0
        self._stale = False

        w, l = settings.stock_width, settings.stock_length
        self._stock = QRectF(0, 0, w, l)
        self._scene.setSceneRect(self._stock.adjusted(-_PADDING, -_PADDING, _PADDING, _PADDING))
        stock = self._scene.addRect(self._stock, _pen(QColor("#6b7782"), 1.2), QBrush(QColor("#ffffff")))
        stock.setZValue(0)
        for zone in settings.keepouts:
            if zone.shape == "circle":
                r = zone.diameter / 2
                item = self._scene.addEllipse(zone.x - r, zone.y - r, zone.diameter, zone.diameter)
            else:
                item = self._scene.addRect(zone.x, zone.y, zone.width, zone.height)
            item.setPen(_pen(ZONE_COLOR, 1.0))
            item.setBrush(QBrush(QColor(214, 69, 69, 55)))
            item.setToolTip(f"Keep-out zone: {zone.name}")
            item.setZValue(1)
        origin = self._scene.addEllipse(-0.6, -0.6, 1.2, 1.2, _pen(ORIGIN_COLOR, 1.5), QBrush(QColor(255, 255, 255)))
        origin.setZValue(5)
        origin.setToolTip("Origin (X0 Y0): top-left corner of the stock")

    # --- public API ---------------------------------------------------------------------------------

    @property
    def drawn_cut_moves(self) -> int:
        """Number of engraving segments currently drawn (0 when nothing is shown)."""
        return self._drawn_cut_moves

    @property
    def stale(self) -> bool:
        return self._stale

    def show_program(self, gcode: str) -> ParsedProgram:
        """Parse the G-code text and draw it, replacing whatever was drawn before."""
        self.clear_program()
        program = parse_gcode(gcode)
        cut, travel = QPainterPath(), QPainterPath()
        for target, wanted in ((cut, True), (travel, False)):
            last = None
            for move in program.moves:
                if move.cutting != wanted:
                    continue
                start, end = QPointF(move.start[0], -move.start[1]), QPointF(move.end[0], -move.end[1])
                if last != start:
                    target.moveTo(start)  # a new run: do not draw a line across the gap
                target.lineTo(end)
                last = end
        travel_item = self._scene.addPath(travel, _pen(TRAVEL_COLOR, 1.0, dashed=True))
        cut_item = self._scene.addPath(cut, _pen(CUT_COLOR, 2.0))
        travel_item.setZValue(2)
        cut_item.setZValue(3)
        self._program_items = [travel_item, cut_item]
        first = next((m for m in program.moves if m.cutting), None)
        if first is not None:
            x, y = first.start[0], -first.start[1]
            marker = self._scene.addEllipse(x - 0.5, y - 0.5, 1.0, 1.0, _pen(START_COLOR, 1.5), QBrush(START_COLOR))
            marker.setZValue(4)
            marker.setToolTip("First plunge")
            self._program_items.append(marker)
        self._drawn_cut_moves = len(program.cut_moves)
        self.set_stale(False)
        self.fit()
        return program

    def clear_program(self) -> None:
        for item in self._program_items:
            self._scene.removeItem(item)
        self._program_items = []
        self._drawn_cut_moves = 0

    def set_stale(self, stale: bool) -> None:
        """Fade the toolpath: the text changed since it was created, so it no longer matches."""
        self._stale = stale
        for item in self._program_items:
            item.setOpacity(_STALE_OPACITY if stale else 1.0)

    def fit(self) -> None:
        self._auto_fit = True
        self.resetTransform()
        self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    # --- mouse and window events ------------------------------------------------------------------

    def wheelEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self._auto_fit = False
        self.scale(factor, factor)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self.fit()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._auto_fit:
            self.fit()
