import dataclasses
import re

import pytest

from artisancam import create_program
from artisancam.config import KeepOut
from artisancam.font import load_default_font
from artisancam.layout import LayoutError, layout_lines, layout_text
from gcode_check import check
from artisancam.gcode import to_file_bytes

FONT = load_default_font()


def bounds(strokes):
    xs = [x for s in strokes for x, _ in s]
    ys = [y for s in strokes for _, y in s]
    return min(xs), max(xs), min(ys), max(ys)


def with_zones(settings, *zones):
    return dataclasses.replace(settings, keepouts=tuple(zones))


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


# --- keep-out zones ------------------------------------------------------------------------------------


def test_default_config_has_no_zones_so_nothing_is_blocked(settings):
    assert settings.keepouts == ()


def test_rect_zone_far_away_does_not_block(settings):
    s = with_zones(settings, KeepOut("D-cut", "rect", x=10, y=30, width=17, height=12))
    layout_lines("HDMI", "HDMI", FONT, s)


def test_rect_zone_under_the_text_blocks_it_and_is_named(settings):
    s = with_zones(settings, KeepOut("D-cut", "rect", x=10, y=3, width=17, height=6))
    with pytest.raises(LayoutError, match="'D-cut'"):
        layout_text("HDMI", FONT, s)


def test_clearance_is_enforced_around_the_zone(settings):
    # The "I" ink spans y 4.0..7.5 mm; the zone starts 0.5 mm below it (y = 8.0).
    zone = KeepOut("clamp", "rect", x=0, y=8.0, width=37.25, height=5)
    layout_text("I", FONT, with_zones(dataclasses.replace(settings, keepout_clearance=0.4), zone))  # 0.5 away: ok
    with pytest.raises(LayoutError, match="keep-out"):
        layout_text("I", FONT, with_zones(dataclasses.replace(settings, keepout_clearance=0.6), zone))


def test_circle_zone_blocks_when_ink_is_inside_and_clears_when_far(settings):
    middle = settings.stock_width / 2
    hit = with_zones(settings, KeepOut("Screw hole 1", "circle", x=middle, y=5.5, diameter=3.2))
    with pytest.raises(LayoutError, match="Screw hole 1"):
        layout_text("I", FONT, hit)  # the "I" stroke runs straight through this hole
    far = with_zones(settings, KeepOut("Screw hole 1", "circle", x=4, y=5.5, diameter=3.2))
    layout_text("I", FONT, far)


def test_circle_zone_clearance_uses_the_radius_plus_clearance(settings):
    middle = settings.stock_width / 2
    # "I" is a vertical line at x=middle from y=4.0 to 7.5; a hole centred 2.0 mm to the side, r=0.5.
    zone = KeepOut("hole", "circle", x=middle + 2.0, y=5.5, diameter=1.0)
    # The zone reaches r + clearance = 0.5 + clearance from the hole centre; the stroke is 2.0 mm away.
    layout_text("I", FONT, with_zones(dataclasses.replace(settings, keepout_clearance=1.4), zone))  # reaches 1.9: clear
    with pytest.raises(LayoutError):
        layout_text("I", FONT, with_zones(dataclasses.replace(settings, keepout_clearance=1.6), zone))  # reaches 2.1: hit


def test_a_zone_blocks_the_bottom_line_too(settings):
    s = with_zones(settings, KeepOut("hole", "circle", x=settings.stock_width / 2, y=settings.stock_length - 5.5, diameter=3))
    layout_text("I", FONT, s, "top")
    with pytest.raises(LayoutError, match="^Bottom text: .*hole"):
        layout_text("I", FONT, s, "bottom")


def test_a_segment_crossing_a_zone_without_an_endpoint_inside_is_caught(settings):
    # "-" is one long horizontal segment; a thin zone in the middle has no vertex of the stroke inside it.
    s = dataclasses.replace(settings, keepout_clearance=0.0, top_margin=4.0)
    ink = layout_text("-", FONT, s)
    (x0, y), (x1, _) = ink[0][0], ink[0][-1]
    zone = KeepOut("thin", "rect", x=(x0 + x1) / 2 - 0.1, y=y - 1.0, width=0.2, height=2.0)
    with pytest.raises(LayoutError, match="thin"):
        layout_text("-", FONT, with_zones(s, zone))


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
