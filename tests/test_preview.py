import dataclasses
import math
import re

import pytest

from artisancam import create_program
from artisancam.config import Cutout
from artisancam.preview import d_outline, parse_gcode
from conftest import REFERENCE

SAMPLE = "\r\n".join(
    [
        ";comment G1 X999",
        "M3 P100",
        "G4 S2",
        "G21",
        "G90",
        "G0 X0 Y0 Z10",
        "G0 X5 Y-5 Z10",
        "G0 X5 Y-5 Z5",
        "G1 X5 Y-5 Z-0.2 F300",
        "G1 X10 Y-5 Z-0.2 F1600",
        "G1 X12 F1600",  # omitted axes keep their last value
        "G1 X12 Y-5 Z5 F700",
        "G0 X0 Y0 Z10",
        "M5",
        "",
    ]
)


def test_moves_are_classified_as_cut_or_travel():
    p = parse_gcode(SAMPLE)
    assert [(m.start, m.end, m.cutting) for m in p.moves] == [
        ((0, 0), (5, -5), False),
        ((5, -5), (10, -5), True),
        ((10, -5), (12, -5), True),  # X-only move: Y and Z carried over
        ((12, -5), (0, 0), False),
    ]
    assert p.strokes == 1
    assert p.cut_length == pytest.approx(7.0)
    assert len(p.cut_moves) == 2


def test_comments_and_other_commands_add_nothing():
    p = parse_gcode(";G1 X5 Y5 Z-1\nM3 P100\nG4 S2\nG21\nG90\nM5\n")
    assert p.moves == () and p.strokes == 0


def test_a_move_above_the_stock_or_a_rapid_below_it_is_travel():
    above = parse_gcode("G0 X0 Y0 Z5\nG1 X5 Y0 Z1 F100\n")
    assert [m.cutting for m in above.moves] == [False]
    rapid_below = parse_gcode("G0 X0 Y0 Z5\nG1 X0 Y0 Z-0.2 F100\nG0 X5 Y0\n")
    assert [m.cutting for m in rapid_below.moves] == [False]


def test_each_plunge_counts_as_one_stroke():
    text = "G0 X0 Y0 Z5\nG1 X0 Y0 Z-0.2 F1\nG1 X1 Y0 F1\nG1 X1 Y0 Z5 F1\nG0 X3 Y0 Z5\nG1 X3 Y0 Z-0.2 F1\nG1 X4 Y0 F1\n"
    assert parse_gcode(text).strokes == 2


def test_generated_program_round_trips(settings):
    program = create_program("HDMI OUT", settings, bottom="Öl")
    parsed = parse_gcode(program)
    plunges = [line for line in program.splitlines() if line.endswith("F333.3")]
    assert parsed.strokes == len(plunges) > 0
    assert parsed.cut_length > 0
    assert all(0 <= m.start[0] <= settings.stock_width and 0 <= m.end[0] <= settings.stock_width for m in parsed.moves)
    assert all(m.start[1] <= 0 and m.end[1] <= 0 for m in parsed.moves)  # top-left origin: Y never positive
    cut_lines = [l for l in program.splitlines() if l.startswith("G1") and l.endswith("F1600")]
    assert 0 < len(parsed.cut_moves) <= len(cut_lines)


@pytest.mark.skipif(not REFERENCE.exists(), reason="reference/HDMI_OUT_v4.cnc not present")
def test_the_reference_program_has_ten_strokes():
    assert parse_gcode(REFERENCE.read_text()).strokes == 10


# --- the widget -----------------------------------------------------------------------------------------


def _render(view, width=346, height=552):
    """Render the scene (scene rect has the aspect 43.25 x 69) to an image, one pixel per sample."""
    from PySide6.QtGui import QColor, QImage, QPainter

    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    view.scene().render(painter)
    painter.end()
    return image


def _green_rows(image):
    rows = []
    for y in range(image.height()):
        for x in range(image.width()):
            c = image.pixelColor(x, y)
            if c.green() > c.red() + 60 and c.green() > c.blue() + 30:
                rows.append(y)
                break
    return rows


@pytest.fixture
def view(qapp, settings):
    from artisancam.ui.preview_view import PreviewView

    v = PreviewView(settings)
    v.resize(400, 600)
    yield v
    v.close()


def test_nothing_is_drawn_before_a_program_is_shown(view):
    assert view.drawn_cut_moves == 0
    assert _green_rows(_render(view)) == []


def test_show_program_draws_exactly_the_parsed_cut_moves(view, settings):
    program = create_program("HDMI", settings)
    parsed = view.show_program(program)
    assert parsed.strokes > 0
    assert view.drawn_cut_moves == len(parsed.cut_moves) > 0
    assert _green_rows(_render(view))


def test_clear_program_removes_the_drawing(view, settings):
    view.show_program(create_program("HDMI", settings))
    view.clear_program()
    assert view.drawn_cut_moves == 0
    assert _green_rows(_render(view)) == []


def test_showing_a_second_program_replaces_the_first(view, settings):
    view.show_program(create_program("HDMI OUT", settings))
    first = view.drawn_cut_moves
    view.show_program(create_program("I", settings))
    assert 0 < view.drawn_cut_moves < first


def test_picture_is_not_upside_down(view, settings):
    top = _green_rows(_render(view) if view.show_program(create_program("HDMI", settings)) else None)
    assert top and max(top) < 552 * 0.25  # top text: in the upper quarter of the picture
    view.show_program(create_program("", settings, bottom="HDMI"))
    bottom = _green_rows(_render(view))
    assert bottom and min(bottom) > 552 * 0.75  # bottom text: in the lower quarter


def _green_pixels(image):
    return [
        (x, y)
        for y in range(image.height())
        for x in range(image.width())
        if (c := image.pixelColor(x, y)).green() > c.red() + 60 and c.green() > c.blue() + 30
    ]


def test_picture_is_not_mirrored_left_to_right(view, settings):
    # "L" is a vertical stem with a foot pointing right at the bottom. Mirrored, the foot would point left.
    # Fixed letter size, so the pixel distances below do not depend on the values tuned in config.toml.
    fixed = dataclasses.replace(settings, top_height=3.5, top_margin=4.0)
    view.show_program(create_program("L", fixed))
    pixels = _green_pixels(_render(view))
    ys = [y for _, y in pixels]
    top, bottom = min(ys), max(ys)
    stem_x = [x for x, y in pixels if y < top + (bottom - top) * 0.3]  # upper part of the letter: stem only
    foot_x = [x for x, y in pixels if y > bottom - 3]  # the bottom rows: stem plus foot
    assert stem_x and foot_x
    assert max(foot_x) > max(stem_x) + 10  # the foot reaches to the right of the stem
    assert min(foot_x) <= min(stem_x) + 2  # and starts at the stem


def _reddish(c):
    return c.red() > c.green() + 20 and c.red() > c.blue() + 20


def _px(image, x_mm, y_mm):
    sx, sy = 346 / 43.25, 552 / 69  # the scene rect starts at (-3, -3) and is 43.25 x 69 mm
    return image.pixelColor(round((x_mm + 3) * sx), round((y_mm + 3) * sy))


def _two_versions(settings):
    return dataclasses.replace(
        settings,
        cutouts=(
            Cutout("hole", "A", "circle", x=10, y=30, diameter=4),
            Cutout("slot", "B", "rect", x=20, y=30, width=8, height=6),
        ),
    )


def test_first_cutout_version_is_drawn_red_by_default(qapp, settings):
    from artisancam.ui.preview_view import PreviewView

    v = PreviewView(_two_versions(settings))
    assert v.cutout_version == "A" and v.drawn_cutouts == 1
    image = _render(v)
    assert _reddish(_px(image, 10, 30))
    assert not _reddish(_px(image, 24, 33))  # version B's slot is not drawn
    v.close()


def test_switching_the_version_swaps_the_red_shapes(qapp, settings):
    from artisancam.ui.preview_view import PreviewView

    v = PreviewView(_two_versions(settings))
    v.set_cutout_version("B")
    image = _render(v)
    assert _reddish(_px(image, 24, 33)) and not _reddish(_px(image, 10, 30))
    v.set_cutout_version(None)
    assert v.drawn_cutouts == 0 and not _reddish(_px(_render(v), 24, 33))
    v.close()


def test_a_d_cutout_with_a_flat_is_drawn_with_the_flat(qapp, settings):
    from artisancam.ui.preview_view import PreviewView

    d = Cutout("D", "A", "d", x=18, y=30, diameter=24, flat=6, flat_side="bottom")
    v = PreviewView(dataclasses.replace(settings, cutouts=(d,)))
    image = _render(v)
    assert _reddish(_px(image, 18, 33))  # inside, above the flat (flat is at y = 36)
    assert not _reddish(_px(image, 18, 39))  # below the flat the circle would still reach y = 42
    v.close()


def test_cutouts_do_not_draw_any_engraving(qapp, settings):
    from artisancam.ui.preview_view import PreviewView

    v = PreviewView(_two_versions(settings))
    assert v.drawn_cut_moves == 0 and _green_rows(_render(v)) == []
    v.close()


@pytest.mark.parametrize("side", ["left", "right", "top", "bottom"])
def test_d_outline_is_a_circle_cut_off_at_the_flat(side):
    pts = d_outline(18, 30, 24, 6, side)
    assert all(math.dist(p, (18, 30)) <= 12 + 1e-9 for p in pts)
    axis, sign = {"left": (0, -1), "right": (0, 1), "top": (1, -1), "bottom": (1, 1)}[side]
    limit = (18, 30)[axis] + sign * 6
    assert max(sign * (p[axis] - limit) for p in pts) == pytest.approx(0)  # nothing beyond the flat
    assert sum(1 for p in pts if abs(p[axis] - limit) < 1e-9) > 10  # many points lie on the flat itself


def test_d_outline_rejects_an_unknown_side():
    with pytest.raises(ValueError):
        d_outline(0, 0, 24, 6, "middle")


def _darkest(image, from_row=40):
    # Rows above 40 px hold the black reference-point symbol at the origin; it never fades, so skip them.
    return min(
        image.pixelColor(x, y).red() + image.pixelColor(x, y).green() + image.pixelColor(x, y).blue()
        for y in range(from_row, image.height()) for x in range(image.width())
    )


def test_stale_fades_the_toolpath_and_a_new_program_restores_it(view, settings):
    fixed = dataclasses.replace(settings, top_height=3.5, top_margin=4.0)  # text below row 40, any config
    view.show_program(create_program("HDMI", fixed))
    normal = _darkest(_render(view))
    view.set_stale(True)
    assert view.stale
    assert _darkest(_render(view)) > normal + 60  # visibly lighter
    view.show_program(create_program("HDMI", fixed))
    assert not view.stale
    assert _darkest(_render(view)) == normal


# --- the reference-point symbol ----------------------------------------------------------------------


def _dark(c):
    return c.red() + c.green() + c.blue() < 200


def test_reference_point_sits_on_the_cover_corner(view):
    from PySide6.QtWidgets import QGraphicsItem

    marker = view.reference_marker
    assert marker.scene() is view.scene()
    assert (marker.pos().x(), marker.pos().y()) == (0, 0)  # scene (0, 0) = top-left corner = G-code X0 Y0
    assert marker.flags() & QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations
    assert "X0 Y0" in marker.toolTip()


def test_reference_point_is_quartered_black_and_white(view):
    image = _render(view)
    cx = cy = round(3 * 346 / 43.25)  # the corner is 3 mm (padding) from the image edge: 24 px
    assert _dark(image.pixelColor(cx + 4, cy - 4))  # top-right: black
    assert _dark(image.pixelColor(cx - 4, cy + 4))  # bottom-left: black
    assert not _dark(image.pixelColor(cx - 4, cy - 4))  # top-left: white
    assert not _dark(image.pixelColor(cx + 4, cy + 4))  # bottom-right: white


def test_reference_point_keeps_its_size_when_zooming(view):
    view.scale(4, 4)
    on_screen = view.reference_marker.deviceTransform(view.viewportTransform())
    assert on_screen.m11() == pytest.approx(1.0)  # not scaled with the view


def test_reference_point_is_drawn_once_after_new_settings(view, settings):
    from artisancam.ui.preview_view import ReferenceMarker

    view.set_settings(dataclasses.replace(settings, stock_length=70))
    markers = [i for i in view.scene().items() if isinstance(i, ReferenceMarker)]
    assert markers == [view.reference_marker]


def test_fit_resets_a_manual_zoom(view):
    view.fit()
    base = view.transform().m11()
    view.scale(3, 3)
    assert view.transform().m11() == pytest.approx(base * 3)
    view.fit()
    assert view.transform().m11() == pytest.approx(base)
