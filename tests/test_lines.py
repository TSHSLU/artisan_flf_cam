import dataclasses
import re

import pytest

from artisancam import create_program
from artisancam.config import Cutout
from artisancam.font import load_default_font
from artisancam.layout import LayoutError, layout_lines, layout_text
from gcode_check import check
from artisancam.gcode import to_file_bytes

FONT = load_default_font()


def bounds(strokes):
    xs = [x for s in strokes for x, _ in s]
    ys = [y for s in strokes for _, y in s]
    return min(xs), max(xs), min(ys), max(ys)


# --- bottom line ---------------------------------------------------------------------------------


def test_bottom_caps_sit_on_a_baseline_bottom_margin_above_the_edge(settings):
    _, _, top, bottom = bounds(layout_text("HDMI", FONT, settings, "bottom"))
    assert bottom == pytest.approx(settings.stock_length - settings.bottom_margin)
    assert bottom - top == pytest.approx(settings.bottom_height)


def test_bottom_text_is_centred_too(settings):
    left, right, _, _ = bounds(layout_text("Rückseite", FONT, settings, "bottom"))
    assert (left + right) / 2 == pytest.approx(settings.stock_width / 2)


def test_bottom_and_top_can_have_different_heights(settings):
    s = dataclasses.replace(settings, bottom_height=2.0)
    _, _, top, bottom = bounds(layout_text("HDMI", FONT, s, "bottom"))
    assert bottom - top == pytest.approx(2.0)


def test_descender_below_the_bottom_baseline_is_checked_against_the_edge(settings):
    s = dataclasses.replace(settings, bottom_margin=1.2)  # baseline fits, a "g" descender does not
    layout_text("HDMI", FONT, s, "bottom")
    with pytest.raises(LayoutError, match="too low or too high"):
        layout_text("g", FONT, s, "bottom")


# --- both lines / either line / neither ---------------------------------------------------------------


def test_either_line_alone_or_both(settings):
    top_only = layout_lines("HDMI", "", FONT, settings)
    bottom_only = layout_lines("", "HDMI", FONT, settings)
    both = layout_lines("HDMI", "HDMI", FONT, settings)
    assert len(both) == len(top_only) + len(bottom_only)
    assert bounds(top_only)[3] < settings.stock_length / 2 < bounds(bottom_only)[2]


def test_a_blank_or_space_only_line_is_ignored(settings):
    assert layout_lines("HDMI", "   ", FONT, settings) == layout_lines("HDMI", "", FONT, settings)


def test_no_text_at_all_is_rejected(settings):
    with pytest.raises(LayoutError, match="top text, a bottom text, or both"):
        layout_lines("", "  ", FONT, settings)


def test_errors_name_the_offending_line(settings):
    with pytest.raises(LayoutError, match="^Bottom text: .*too wide"):
        layout_lines("HDMI", "HDMI-OUT HDMI-OUT", FONT, settings)
    with pytest.raises(LayoutError, match="^Top text: The font has no glyph for: '日'"):
        layout_lines("日", "HDMI", FONT, settings)


def test_overlapping_lines_are_rejected(settings):
    s = dataclasses.replace(settings, bottom_margin=settings.stock_length - settings.top_margin - 2.0)
    with pytest.raises(LayoutError, match="too close together"):
        layout_lines("HDMI", "HDMI", FONT, s)


# --- cut-outs are only drawn, never block ---------------------------------------------------------------


def test_text_over_a_cutout_is_not_blocked(settings):
    # A hole drawn right under the top text must not stop the program or change the G-code.
    hole = Cutout("hole", "1xD", "rect", x=5, y=3, width=27, height=6)
    covered = dataclasses.replace(settings, cutouts=(hole,))
    bare = dataclasses.replace(settings, cutouts=())
    assert create_program("HDMI OUT", covered, bottom="Test") == create_program("HDMI OUT", bare, bottom="Test")


# --- whole pipeline ------------------------------------------------------------------------------------


@pytest.mark.parametrize("top,bottom", [("HDMI OUT", ""), ("", "HDMI IN"), ("HDMI OUT", "HDMI IN"), ("Äpfel", "Öl & Müß")])
def test_programs_with_either_or_both_lines_pass_the_checker(settings, top, bottom):
    program = create_program(top, settings, bottom=bottom)
    problems = check(
        to_file_bytes(program), stock_width=settings.stock_width, stock_length=settings.stock_length,
        depth=settings.depth, retract_z=settings.retract_z, edge_margin=settings.edge_margin,
    )
    assert problems == []


def test_both_lines_appear_in_the_program(settings):
    ys = [float(m) for m in re.findall(r" Y(-\d+\.\d+)", create_program("HDMI", settings, bottom="HDMI"))]
    assert max(ys) > -8.5          # top text lies near Y=0 (4.0..7.5 mm below the top edge)
    assert min(ys) < -settings.stock_length + 8.5  # bottom text lies near the far end


def test_label_in_the_header_lists_both_lines(settings):
    assert ";Text: Ärger / Öl" not in create_program("Ärger", settings, bottom="Öl")  # comments are ASCII-only
    assert ";Text: Aerger / Oel" in create_program("Ärger", settings, bottom="Öl")


def test_no_text_raises_for_the_pipeline_too(settings):
    with pytest.raises(LayoutError):
        create_program("", settings)
