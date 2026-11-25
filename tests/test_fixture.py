"""Several covers in one run: slot positions, the combined program, the checker and the preview."""

import dataclasses
import re

import pytest

from artisancam import create_program, create_program_for_slots
from artisancam.config import ConfigError, Settings, parse_settings, values_of
from artisancam.fixture import fixture_size, shift, slot_offsets
from artisancam.gcode import to_file_bytes
from artisancam.layout import LayoutError
from artisancam.preview import parse_gcode
from conftest import ROOT
from gcode_check import check

GOLDEN = ROOT / "tests" / "golden" / "single_cover_hdmi_out.cnc"


def fixed_single_cover() -> Settings:
    """The values the golden file was made with (before multi-cover support), plus a 1 x 1 fixture."""
    return Settings(
        stock_width=37.25, stock_length=62.5, letter_gap=460, space_width=380, edge_margin=1.0,
        top_height=3.5, top_margin=4.0, bottom_height=3.5, bottom_margin=5.0, depth=0.2,
        clearance_z=10, retract_z=5, feed_z=5, cutting_feed=1600, plunge_feed=333.3, retract_feed=700,
        spindle_percent=100, spindle_warmup_s=2,
        fixture_columns=1, fixture_rows=1, pitch_x=45.0, pitch_y=70.0,
    )


def verify(program, s):
    return check(
        to_file_bytes(program), stock_width=s.stock_width, stock_length=s.stock_length, depth=s.depth,
        retract_z=s.retract_z, edge_margin=s.edge_margin,
        columns=s.columns, rows=s.rows, pitch_x=s.pitch_x, pitch_y=s.pitch_y,
    )


# --- one cover stays exactly as before -------------------------------------------------------------------


def test_single_cover_output_is_byte_identical_to_before():
    expected = GOLDEN.read_bytes()
    s = fixed_single_cover()
    assert to_file_bytes(create_program_for_slots([("HDMI OUT", "Rückseite")], s)) == expected
    assert to_file_bytes(create_program("HDMI OUT", s, bottom="Rückseite")) == expected


def test_create_program_ignores_the_fixture(six_slots):
    # The single-cover shortcut always engraves one cover at the origin, whatever the fixture.
    one = dataclasses.replace(six_slots, fixture_columns=1, fixture_rows=1)
    assert create_program("HDMI", six_slots) == create_program("HDMI", one)


# --- slot positions ---------------------------------------------------------------------------------------


def test_slot_offsets_go_row_by_row(six_slots):
    assert slot_offsets(six_slots) == [(0, 0), (45, 0), (90, 0), (0, 70), (45, 70), (90, 70)]


def test_one_slot_and_one_row(settings):
    assert slot_offsets(settings) == [(0, 0)]
    three = dataclasses.replace(settings, fixture_columns=3, fixture_rows=1, pitch_x=40.0)
    assert slot_offsets(three) == [(0, 0), (40, 0), (80, 0)]


def test_fixture_size_spans_all_slots(six_slots):
    assert fixture_size(six_slots) == (90 + six_slots.stock_width, 70 + six_slots.stock_length)


def test_shift_moves_every_point():
    assert shift([[(1, 2), (3, 4)]], 10, 20) == [[(11, 22), (13, 24)]]


# --- the combined program ------------------------------------------------------------------------------------


def _cut_points(program):
    return [(m.start, m.end) for m in parse_gcode(program).cut_moves]


@pytest.mark.parametrize("slot,dx,dy", [(1, 45, 0), (2, 90, 0), (3, 0, 70), (5, 90, 70)])
def test_a_slot_is_slot_1_moved_by_its_offset(six_slots, slot, dx, dy):
    texts = [("", "")] * 6
    first = list(texts)
    first[0] = ("HDMI OUT", "Rückseite")
    other = list(texts)
    other[slot] = ("HDMI OUT", "Rückseite")
    a, b = _cut_points(create_program_for_slots(first, six_slots)), _cut_points(create_program_for_slots(other, six_slots))
    assert len(a) == len(b) > 0
    for (sa, ea), (sb, eb) in zip(a, b):  # machine Y is -y, so a slot further down has a more negative Y
        assert sb == pytest.approx((sa[0] + dx, sa[1] - dy), abs=1e-3)
        assert eb == pytest.approx((ea[0] + dx, ea[1] - dy), abs=1e-3)


def test_six_covers_pass_the_independent_checker(six_slots):
    program = create_program_for_slots([("HDMI OUT", "Rückseite")] * 6, six_slots)
    assert verify(program, six_slots) == []
    assert parse_gcode(program).strokes == 6 * parse_gcode(create_program("HDMI OUT", six_slots, bottom="Rückseite")).strokes


def test_the_checker_uses_the_whole_fixture(six_slots):
    program = to_file_bytes(create_program_for_slots([("HDMI", "")] * 6, six_slots))
    # Checked as if it were a single cover, the other slots lie outside the stock:
    problems = check(program, stock_width=six_slots.stock_width, stock_length=six_slots.stock_length,
                     depth=six_slots.depth, retract_z=six_slots.retract_z, edge_margin=six_slots.edge_margin)
    assert any("leaves the stock" in p for p in problems)


def test_header_lists_the_fixture_and_each_engraved_slot(six_slots):
    program = create_program_for_slots([("A", ""), ("", ""), ("Ö", "Ü")], six_slots)
    assert ";Fixture 3 x 2 slots, pitch 45.000 x 70.000 mm, origin = top-left corner of slot 1" in program
    assert ";Slot 1: A" in program and ";Slot 3: Oe / Ue" in program and ";Slot 2" not in program
    to_file_bytes(program)  # still pure ASCII


def test_blank_slots_are_skipped_and_all_blank_is_an_error(six_slots):
    with pytest.raises(LayoutError, match="at least one slot"):
        create_program_for_slots([("", " ")] * 6, six_slots)


def test_errors_name_the_slot(six_slots):
    with pytest.raises(LayoutError, match="^Slot 2: Top text: The font has no glyph"):
        create_program_for_slots([("ok", ""), ("日", "")], six_slots)


def test_more_texts_than_slots_is_a_programming_error(six_slots):
    with pytest.raises(ValueError, match="only 6 slots"):
        create_program_for_slots([("A", "")] * 7, six_slots)


def test_fewer_texts_than_slots_is_fine(six_slots):
    assert ";Slot 1: A" in create_program_for_slots([("A", "")], six_slots)


# --- config validation -----------------------------------------------------------------------------------------


def _raw(**fixture):
    import tomllib

    raw = tomllib.loads((ROOT / "config.toml").read_text(encoding="utf-8"))
    raw["fixture"].update(fixture)
    return raw


@pytest.mark.parametrize(
    "fixture,message",
    [
        ({"columns": 0}, r"\[fixture\] columns must be > 0"),
        ({"rows": 2.5}, "whole number from 1 to 10"),
        ({"columns": 11}, "whole number from 1 to 10"),
        ({"columns": 2, "pitch_x": 30.0}, "pitch_x 30 mm is smaller than the cover width"),
        ({"rows": 2, "pitch_y": 60.0}, "pitch_y 60 mm is smaller than the cover length"),
    ],
)
def test_bad_fixtures_are_rejected(fixture, message):
    with pytest.raises(ConfigError, match=message):
        parse_settings(_raw(**fixture))


def test_pitch_only_matters_with_more_than_one_slot_in_that_direction():
    s = parse_settings(_raw(columns=1, rows=1, pitch_x=1.0, pitch_y=1.0))
    assert s.slot_count == 1


def test_fixture_values_are_regular_settings(settings):
    assert {"fixture_columns", "fixture_rows", "pitch_x", "pitch_y"} <= set(values_of(settings))


# --- the preview --------------------------------------------------------------------------------------------------


@pytest.fixture
def view6(qapp, six_slots):
    from artisancam.ui.preview_view import PreviewView

    v = PreviewView(six_slots)
    v.resize(500, 500)
    yield v
    v.close()


def test_preview_draws_six_numbered_slots_and_one_reference_point(view6, six_slots):
    from PySide6.QtWidgets import QGraphicsSimpleTextItem

    from artisancam.ui.preview_view import ReferenceMarker

    assert view6.slot_count == 6
    numbers = sorted(i.text() for i in view6.scene().items() if isinstance(i, QGraphicsSimpleTextItem))
    assert numbers == ["1", "2", "3", "4", "5", "6"]
    assert [i for i in view6.scene().items() if isinstance(i, ReferenceMarker)] == [view6.reference_marker]
    w, l = fixture_size(six_slots)
    assert view6.sceneRect().width() == pytest.approx(w + 6) and view6.sceneRect().height() == pytest.approx(l + 6)


def test_preview_draws_the_cutouts_in_every_slot(view6, six_slots):
    per_cover = sum(1 for c in six_slots.cutouts if c.version == view6.cutout_version)
    assert view6.drawn_cutouts == 6 * per_cover


def test_preview_renders_engraving_in_every_slot(view6, six_slots):
    from PySide6.QtGui import QColor, QImage, QPainter

    view6.show_program(create_program_for_slots([("HDMI OUT", "Rückseite")] * 6, six_slots))
    rect = view6.sceneRect()
    k = 6  # pixels per mm
    image = QImage(round(rect.width() * k), round(rect.height() * k), QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    view6.scene().render(painter)
    painter.end()
    for dx, dy in slot_offsets(six_slots):
        # The top text area of this slot (scene rect starts 3 mm before slot 1's corner).
        x0, x1 = round((dx + 3) * k), round((dx + 3 + six_slots.stock_width) * k)
        y0, y1 = round((dy + 3) * k), round((dy + 3 + 10) * k)
        green = any(
            (c := image.pixelColor(x, y)).green() > c.red() + 60
            for y in range(y0, y1, 2) for x in range(x0, x1, 2)
        )
        assert green, f"no engraving drawn in the slot at {dx}, {dy}"


def test_slot_states_must_match_the_slot_count(view6):
    with pytest.raises(ValueError):
        view6.set_slot_states([True, False])
    view6.set_slot_states([True, False, True, False, True, False])
    assert view6.filled_slots == (True, False, True, False, True, False)
