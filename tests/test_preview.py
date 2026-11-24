import dataclasses
import re

import pytest

from artisancam import create_program
from artisancam.config import KeepOut
from artisancam.preview import parse_gcode
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
    view.show_program(create_program("L", settings))
    pixels = _green_pixels(_render(view))
    ys = [y for _, y in pixels]
    top, bottom = min(ys), max(ys)
    stem_x = [x for x, y in pixels if y < top + (bottom - top) * 0.3]  # upper part of the letter: stem only
    foot_x = [x for x, y in pixels if y > bottom - 3]  # the bottom rows: stem plus foot
    assert stem_x and foot_x
    assert max(foot_x) > max(stem_x) + 10  # the foot reaches to the right of the stem
    assert min(foot_x) <= min(stem_x) + 2  # and starts at the stem


def test_keepout_zones_are_drawn_reddish(qapp, settings):
    from artisancam.ui.preview_view import PreviewView

    s = dataclasses.replace(settings, keepouts=(KeepOut("hole", "circle", x=10, y=30, diameter=4),))
    v = PreviewView(s)
    image = _render(v)
    sx, sy = 346 / 43.25, 552 / 69  # scene rect starts at (-3, -3)
    c = image.pixelColor(round((10 + 3) * sx), round((30 + 3) * sy))
    assert c.red() > c.green() + 20 and c.red() > c.blue() + 20
    outside = image.pixelColor(round((30 + 3) * sx), round((30 + 3) * sy))
    assert outside.red() == outside.green() == outside.blue()  # plain stock elsewhere
    v.close()


def _darkest(image):
    return min(
        image.pixelColor(x, y).red() + image.pixelColor(x, y).green() + image.pixelColor(x, y).blue()
        for y in range(image.height()) for x in range(image.width())
    )


def test_stale_fades_the_toolpath_and_a_new_program_restores_it(view, settings):
    view.show_program(create_program("HDMI", settings))
    normal = _darkest(_render(view))
    view.set_stale(True)
    assert view.stale
    assert _darkest(_render(view)) > normal + 60  # visibly lighter
    view.show_program(create_program("HDMI", settings))
    assert not view.stale
    assert _darkest(_render(view)) == normal


def test_fit_resets_a_manual_zoom(view):
    view.fit()
    base = view.transform().m11()
    view.scale(3, 3)
    assert view.transform().m11() == pytest.approx(base * 3)
    view.fit()
    assert view.transform().m11() == pytest.approx(base)
