import math
import string

from artisancam.font import arc_points, load_default_font, parse_font

FONT = load_default_font()


def test_required_characters_exist():
    needed = string.ascii_letters + string.digits + " -_.,:;/()+" + "äöüÄÖÜß"
    assert FONT.missing(needed) == []


def test_cap_height():
    assert FONT.cap_height == 900


def test_h_is_three_strokes_and_d_is_one():
    assert len(FONT.glyphs["H"]) == 3
    assert len(FONT.glyphs["D"]) == 1  # connected segments are joined into one cut


def test_space_has_no_strokes():
    assert FONT.glyphs[" "] == ()


def test_umlaut_is_base_letter_plus_dots():
    assert len(FONT.glyphs["ä"]) == len(FONT.glyphs["a"]) + 2
    assert len(FONT.glyphs["Ö"]) == len(FONT.glyphs["O"]) + 2


def test_unknown_characters_are_reported_once_in_order():
    assert FONT.missing("a日b日€") == ["日", "€"]


def test_arc_lies_on_the_circle_and_bulges_outward():
    # The corner arc of the lowercase "a": from (600,600) to (750,450), centre (600,450), r=150.
    points = arc_points((600, 600), 150, large=False, sweep=False, end=(750, 450))
    assert points[-1] == (750, 450)
    assert all(math.isclose(math.dist(p, (600, 450)), 150, abs_tol=1e-6) for p in points)
    # Clockwise from 90 degrees to 0: it passes through the 45 degree point, upper right of the centre.
    corner = (600 + 150 * math.cos(math.pi / 4), 450 + 150 * math.sin(math.pi / 4))
    assert min(math.dist(p, corner) for p in points) <= 150 * math.radians(5) + 1  # half a 10-degree step
    # Steps are at most 10 degrees.
    angles = [math.atan2(y - 450, x - 600) for x, y in [(600, 600)] + points]
    assert all(abs(a - b) <= math.radians(10) + 1e-9 for a, b in zip(angles, angles[1:]))


def test_large_and_small_arcs_choose_different_centres():
    small = arc_points((0, 0), 10, large=False, sweep=True, end=(10, 10))
    large = arc_points((0, 0), 10, large=True, sweep=True, end=(10, 10))
    assert small != large
    assert max(abs(p[0]) for p in large) > 10  # the large arc swings outside the chord box


def test_malformed_font_is_rejected():
    import pytest
    from artisancam.font import FontError

    with pytest.raises(FontError):
        parse_font("<svg>not a font")
