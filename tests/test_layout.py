import dataclasses

import pytest

from artisancam.font import load_default_font
from artisancam.layout import LayoutError, layout_text

FONT = load_default_font()


def bounds(strokes):
    xs = [x for s in strokes for x, _ in s]
    ys = [y for s in strokes for _, y in s]
    return min(xs), max(xs), min(ys), max(ys)


def test_capital_letters_have_the_configured_height(settings):
    _, _, top, bottom = bounds(layout_text("HDMI", FONT, settings))
    assert top == pytest.approx(settings.top_margin)
    assert bottom - top == pytest.approx(settings.top_height)


def test_text_is_centred_on_the_stock(settings):
    left, right, _, _ = bounds(layout_text("HDMI-OUT", FONT, settings))
    assert (left + right) / 2 == pytest.approx(settings.stock_width / 2)
    assert 0 < left and right < settings.stock_width


def test_matches_the_fusion_reference_proportions(settings):
    # The program that ran on the machine engraved "HDMI OUT" (its 10 strokes contain no hyphen)
    # at 3.51 mm capital height and spans X 6.106..30.520 (24.414 mm). Letters and the space
    # follow the same proportional spacing; the remaining 0.08 mm comes from the narrow "I".
    s = dataclasses.replace(settings, top_height=3.51)
    left, right, top, bottom = bounds(layout_text("HDMI OUT", FONT, s))
    assert right - left == pytest.approx(24.414, abs=0.1)
    assert bottom - top == pytest.approx(3.51, abs=0.001)


def test_spacing_is_proportional(settings):
    def width(text):
        left, right, _, _ = bounds(layout_text(text, FONT, settings))
        return right - left

    gap = settings.letter_gap * settings.top_height / FONT.cap_height
    # "II" is two zero-width strokes separated by exactly one letter gap, no matter how narrow the glyph.
    assert width("II") == pytest.approx(gap)
    # Each space adds space_width on top of the normal gap.
    extra = settings.space_width * settings.top_height / FONT.cap_height
    assert width("I I") - width("II") == pytest.approx(extra)
    assert width("I  I") - width("I I") == pytest.approx(extra)


def test_leading_and_trailing_spaces_do_not_move_the_text(settings):
    assert bounds(layout_text(" HDMI ", FONT, settings)) == pytest.approx(bounds(layout_text("HDMI", FONT, settings)))


def test_descenders_and_umlaut_dots_stay_on_the_stock(settings):
    _, _, top, bottom = bounds(layout_text("Äpfel gÖß", FONT, settings))
    assert top >= settings.edge_margin
    assert bottom <= settings.stock_length - settings.edge_margin


def test_too_wide_text_is_rejected(settings):
    with pytest.raises(LayoutError, match="too wide"):
        layout_text("HDMI-OUT HDMI-OUT", FONT, settings)


def test_text_too_low_is_rejected(settings):
    s = dataclasses.replace(settings, top_margin=61.0)
    with pytest.raises(LayoutError, match="too low or too high"):
        layout_text("HDMI", FONT, s)


def test_unknown_character_is_named(settings):
    with pytest.raises(LayoutError, match="日"):
        layout_text("A日", FONT, settings)


@pytest.mark.parametrize("text", ["", "   "])
def test_nothing_visible_is_rejected(settings, text):
    with pytest.raises(LayoutError, match="Nothing to engrave"):
        layout_text(text, FONT, settings)


def test_newline_is_rejected(settings):
    with pytest.raises(LayoutError, match="single line"):
        layout_text("A\nB", FONT, settings)
