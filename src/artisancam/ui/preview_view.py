"""2D preview of the finished G-code, seen from above.

It parses the G-code text (see preview.py) and draws it on a QGraphicsScene whose units are
millimetres and whose origin is the stock's top-left corner, x right and y DOWN, the same frame
the cut-outs use. Machine Y is negative below the origin, so the scene uses y = -Y.
Mouse wheel zooms, dragging pans, a double click fits the stock to the view again.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QAbstractGraphicsShapeItem, QGraphicsItem, QGraphicsScene, QGraphicsView

from ..config import Settings
from ..config import Cutout
from ..preview import ParsedProgram, d_outline, parse_gcode

CUT_COLOR = QColor("#0b8a4a")
TRAVEL_COLOR = QColor("#9aa4ad")
CUTOUT_COLOR = QColor("#d64545")
START_COLOR = QColor("#2563eb")
REFERENCE_SIZE_PX = 16  # diameter of the reference-point symbol on screen, whatever the zoom
_PADDING = 3.0  # mm of empty space around the stock in the view
_STALE_OPACITY = 0.25


def _pen(color: QColor, width: float, dashed: bool = False) -> QPen:
    pen = QPen(color, width)
    pen.setCosmetic(True)  # constant width in pixels, whatever the zoom
    if dashed:
        pen.setStyle(Qt.PenStyle.DashLine)
    return pen


class ReferenceMarker(QGraphicsItem):
    """The quartered black-and-white circle that marks the reference point (where X0 Y0 is set).

    It is centred on its position and always drawn REFERENCE_SIZE_PX pixels wide: the flag
    ItemIgnoresTransformations keeps it the same size when the view zooms.
    """

    def __init__(self, diameter_px: float = REFERENCE_SIZE_PX) -> None:
        super().__init__()
        self._radius = diameter_px / 2
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)

    def boundingRect(self) -> QRectF:  # noqa: N802 (Qt naming): the area Qt repaints for this item
        r = self._radius + 1  # +1 pixel for the outline
        return QRectF(-r, -r, 2 * r, 2 * r)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # noqa: ARG002
        r = self._radius
        circle = QRectF(-r, -r, 2 * r, 2 * r)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("white"))
        painter.drawEllipse(circle)
        # drawPie angles are in 1/16 of a degree; 0 is "3 o'clock", positive turns counter-clockwise.
        painter.setBrush(QColor("black"))
        painter.drawPie(circle, 0 * 16, 90 * 16)  # top-right quarter
        painter.drawPie(circle, 180 * 16, 90 * 16)  # bottom-left quarter
        painter.setPen(QPen(QColor("black"), 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(circle)  # outline on top


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
        self._cutout_items: list[QGraphicsItem] = []
        self._cutout_version: str | None = None
        self._drawn_cut_moves = 0
        self._stale = False
        self._stock_items: list[QGraphicsItem] = []
        self.set_settings(settings)
        self.set_cutout_version(settings.cutout_versions[0] if settings.cutout_versions else None)

    # --- public API ---------------------------------------------------------------------------------

    def set_settings(self, settings: Settings) -> None:
        """Redraw the cover outline and cut-outs for new settings. A shown program is removed.

        The chosen cut-out version is kept if it still exists (or if "none" was chosen); otherwise the
        first version is shown.
        """
        self.clear_program()
        for item in self._stock_items:
            self._scene.removeItem(item)
        self.settings = settings
        w, l = settings.stock_width, settings.stock_length
        self._stock = QRectF(0, 0, w, l)
        self._scene.setSceneRect(self._stock.adjusted(-_PADDING, -_PADDING, _PADDING, _PADDING))
        stock = self._scene.addRect(self._stock, _pen(QColor("#6b7782"), 1.2), QBrush(QColor("#ffffff")))
        stock.setZValue(0)
        self.reference_marker = ReferenceMarker()  # placed at scene (0, 0): the cover's top-left corner
        self.reference_marker.setZValue(5)
        self.reference_marker.setToolTip(
            "Reference point: set X0 Y0 here (top-left corner of the cover) and Z0 on the cover's top face"
        )
        self._scene.addItem(self.reference_marker)
        self._stock_items = [stock, self.reference_marker]
        version = self._cutout_version
        if version is not None and version not in settings.cutout_versions:
            version = settings.cutout_versions[0] if settings.cutout_versions else None
        self.set_cutout_version(version)
        if self._auto_fit:
            self.fit()

    @property
    def drawn_cut_moves(self) -> int:
        """Number of engraving segments currently drawn (0 when nothing is shown)."""
        return self._drawn_cut_moves

    @property
    def stale(self) -> bool:
        return self._stale

    @property
    def cutout_version(self) -> str | None:
        """The cut-out version currently drawn in red, or None."""
        return self._cutout_version

    @property
    def drawn_cutouts(self) -> int:
        return len(self._cutout_items)

    def set_cutout_version(self, version: str | None) -> None:
        """Draw the cut-outs of one version in red (None draws none). Display only: the G-code is unaffected."""
        for item in self._cutout_items:
            self._scene.removeItem(item)
        self._cutout_items = []
        self._cutout_version = version
        for cutout in self.settings.cutouts:
            if cutout.version == version:
                item = self._add_cutout(cutout)
                item.setPen(_pen(CUTOUT_COLOR, 1.2))
                item.setBrush(QBrush(QColor(214, 69, 69, 70)))
                item.setToolTip(f"{cutout.name} (cut separately)")
                item.setZValue(1)
                self._cutout_items.append(item)

    def _add_cutout(self, c: Cutout) -> QAbstractGraphicsShapeItem:
        if c.shape == "rect":
            return self._scene.addRect(c.x, c.y, c.width, c.height)
        if c.shape == "d" and c.flat:
            polygon = QPolygonF([QPointF(x, y) for x, y in d_outline(c.x, c.y, c.diameter, c.flat, c.flat_side)])
            return self._scene.addPolygon(polygon)
        r = c.diameter / 2  # a circle, or a D whose flat side is not defined yet
        return self._scene.addEllipse(c.x - r, c.y - r, c.diameter, c.diameter)

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
