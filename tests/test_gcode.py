import dataclasses
import re

import pytest

from artisancam import create_program
from artisancam.gcode import generate_gcode, to_file_bytes
from artisancam.toolpath import Cut, build_toolpath
from conftest import REFERENCE
from gcode_check import check


def verify(program: str, s, **overrides):
    args = dict(stock_width=s.stock_width, stock_length=s.stock_length, depth=s.depth, retract_z=s.retract_z, edge_margin=s.edge_margin)
    return check(to_file_bytes(program), **{**args, **overrides})


@pytest.mark.parametrize("text", ["HDMI-OUT", "Äpfel & Öl", "ß", "i", "Test 12.5", "abcdefgh", "ÜBER", "gjpqy"])
def test_generated_programs_pass_the_independent_checker(settings, text):
    assert verify(create_program(text, settings), settings) == []


def test_program_structure_matches_the_reference_dialect(settings):
    lines = create_program("HDMI-OUT", settings).split("\n")
    code = [line for line in lines if line and not line.startswith(";")]
    assert code[:4] == ["M3 P100", "G4 S2", "G21", "G90"]
    assert code[-2:] == ["G0 X0.000 Y0.000", "M5"]
    assert code[-3].startswith("G0 ") and code[-3].endswith("Z10.000")  # back to clearance height first
    assert all(line.split()[0] in {"M3", "G4", "G21", "G90", "G0", "G1", "M5"} for line in code)
    plunges = [line for line in code if line.endswith("Z-0.200 F333.3")]
    cuts = [line for line in code if line.endswith("Z-0.200 F1600")]
    lifts = [line for line in code if line.endswith("Z5.000 F700")]
    assert len(plunges) == len(lifts) > 0
    assert cuts


def test_every_y_is_negative_for_a_top_left_origin(settings):
    ys = [float(m) for m in re.findall(r" Y(-?\d+\.\d+)", create_program("HDMI-OUT", settings))]
    assert max(ys) <= 0 and min(ys) > -settings.stock_length


def test_depth_comes_from_the_config(settings):
    s = dataclasses.replace(settings, depth=0.35)
    program = create_program("HDMI", s)
    assert "Z-0.350 F333.3" in program and "Z-0.200" not in program
    assert verify(program, s) == []


def test_file_bytes_are_ascii_crlf(settings):
    data = to_file_bytes(create_program("Ärger", settings))
    data.decode("ascii")
    assert data.endswith(b"M5\r\n") and b"\n" not in data.replace(b"\r\n", b"")


def test_comment_with_umlauts_is_ascii(settings):
    assert ";Text: Aerger Oel" in create_program("Ärger Öl", settings)


def test_no_arcs_are_ever_emitted(settings):
    program = create_program("OQ@&8", settings)
    assert not re.search(r"^G[23]\b", program, re.M)


def test_feed_height_below_retract_adds_a_rapid_down(settings):
    s = dataclasses.replace(settings, feed_z=2.0)
    program = create_program("I", s)
    assert re.search(r"G0 X\S+ Y\S+ Z5\.000\nG0 X\S+ Y\S+ Z2\.000\nG1 .* Z-0\.200 F333\.3", program)


def test_toolpath_drops_duplicate_points_and_empty_strokes():
    cuts = build_toolpath([[(0, 0), (0, 0), (1, 0)], [(2, 2)], [(3, 3), (3, 3)]])
    assert cuts == [Cut(((0, 0), (1, 0)))]


def test_generate_refuses_an_empty_program(settings):
    with pytest.raises(ValueError):
        generate_gcode([], settings)


# --- the independent checker must actually catch problems -------------------------------------

GOOD = None


def good(settings):
    return create_program("HDMI", settings)


@pytest.mark.parametrize(
    "mutate,expected",
    [
        (lambda p: p.replace("Z-0.200", "Z-0.900", 1), "deeper than the allowed"),
        (lambda p: p.replace("M3 P100\n", ""), "spindle off"),
        (lambda p: p.replace("G90\n", ""), "before G21/G90"),
        (lambda p: p.replace("M5", ""), "does not end with M5"),
        (lambda p: p.replace("G1 X", "G2 X", 1), "not allowed"),
        (lambda p: p.replace("Z5.000\nG1", "Z0.500\nG1"), "below retract height"),
        (lambda p: re.sub(r"G1 X(\S+) Y(\S+) Z-0.200 F1600", r"G1 X500.000 Y\2 Z-0.200 F1600", p, count=1), "leaves the stock"),
        (lambda p: p.replace(" F1600", "", 1), "without a feed rate"),
    ],
)
def test_checker_catches_broken_programs(settings, mutate, expected):
    problems = verify(mutate(good(settings)), settings)
    assert any(expected in p for p in problems), problems


def test_checker_rejects_lf_only_and_non_ascii(settings):
    program = good(settings)
    assert any("CRLF" in p for p in check(program.encode(), stock_width=37.25, stock_length=63, depth=0.2, retract_z=5))
    assert check("ä".encode(), stock_width=37.25, stock_length=63, depth=0.2, retract_z=5) == ["file is not pure ASCII"]


# --- comparison with the program that was actually run on the machine --------------------------


@pytest.mark.skipif(not REFERENCE.exists(), reason="reference/HDMI_OUT_v4.cnc not present")
def test_the_reference_program_passes_the_checker(settings):
    assert check(REFERENCE.read_bytes(), stock_width=37.25, stock_length=63, depth=0.2, retract_z=5) == []


@pytest.mark.skipif(not REFERENCE.exists(), reason="reference/HDMI_OUT_v4.cnc not present")
def test_stroke_count_and_geometry_match_the_reference(settings):
    ref = REFERENCE.read_text().splitlines()
    s = dataclasses.replace(settings, text_height=3.51, top_margin=4.067)
    ours = create_program("HDMI OUT", s).split("\n")  # the reference contains no hyphen stroke

    def plunges(lines):
        return sum(1 for line in lines if line.endswith("F333.3"))

    def span(lines, axis):
        values = [float(m) for line in lines if line.startswith("G1") for m in re.findall(axis + r"(-?\d+\.\d+)", line)]
        return min(values), max(values)

    assert plunges(ours) == plunges(ref) == 10
    (rx0, rx1), (ox0, ox1) = span(ref, "X"), span(ours, "X")
    assert (ox1 - ox0) == pytest.approx(rx1 - rx0, abs=0.1)
    (ry0, ry1), (oy0, oy1) = span(ref, "Y"), span(ours, "Y")
    assert oy0 == pytest.approx(ry0, abs=0.01) and oy1 == pytest.approx(ry1, abs=0.01)
