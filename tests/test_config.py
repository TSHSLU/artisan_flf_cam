import copy
import tomllib
from pathlib import Path

import pytest

from artisancam.config import ConfigError, load_settings, parse_settings

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def raw():
    return tomllib.loads((ROOT / "config.toml").read_text())


def test_default_config_loads(settings):
    # Sanity only: these values are tuned by the user in config.toml, so tests must not pin them.
    assert settings.stock_width > 0 and settings.stock_length > 0
    assert 0 < settings.depth <= 1.0
    assert 50 < settings.spindle_percent <= 100


def test_missing_key_is_named(raw):
    del raw["feeds"]["cutting"]
    with pytest.raises(ConfigError, match=r"\[feeds\] cutting"):
        parse_settings(raw)


def test_unknown_key_is_rejected(raw):
    raw["engraving"]["dept"] = 0.2
    with pytest.raises(ConfigError, match="Unknown config key"):
        parse_settings(raw)


@pytest.mark.parametrize(
    "section,key,value,message",
    [
        ("engraving", "depth", 2.0, "sanity limit"),
        ("engraving", "depth", 0, "> 0"),
        ("engraving", "depth", -0.2, "> 0"),
        ("spindle", "percent", 40, "above 50"),
        ("spindle", "percent", 120, "at most 100"),
        ("heights", "retract", 20.0, "clearance >= retract >= feed"),
        ("feeds", "cutting", "fast", "must be a number"),
        ("text", "edge_margin", 40, "edge_margin"),
    ],
)
def test_bad_values_are_rejected(raw, section, key, value, message):
    bad = copy.deepcopy(raw)
    bad[section][key] = value
    with pytest.raises(ConfigError, match=message):
        parse_settings(bad)


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_settings(tmp_path / "nope.toml")


# --- text lines and keep-out zones ---------------------------------------------------------------


def test_top_and_bottom_line_settings_load(settings):
    assert settings.top_height > 0 and settings.top_margin >= 0
    assert settings.bottom_height > 0 and settings.bottom_margin >= 0
    # the two lines together must fit on the cover
    assert settings.top_margin + settings.top_height + settings.bottom_height + settings.bottom_margin < settings.stock_length


def test_missing_bottom_key_is_named(raw):
    del raw["text_bottom"]["margin"]
    with pytest.raises(ConfigError, match=r"\[text_bottom\] margin"):
        parse_settings(raw)


def test_the_removed_keepout_clearance_key_is_rejected(raw):
    raw["text"]["keepout_clearance"] = 1.0
    with pytest.raises(ConfigError, match="Unknown config key"):
        parse_settings(raw)


def test_default_config_defines_the_1xd_and_2xd_cutouts(settings):
    assert settings.cutout_versions == ("1xD", "2xD")
    one = {c.name: c for c in settings.cutouts if c.version == "1xD"}
    assert one["D hole"].shape == "d" and one["D hole"].diameter == 24.0
    assert one["Screw hole 1"].x == 9.0 and one["Screw hole 2"].x == 28.0
    two = [c for c in settings.cutouts if c.version == "2xD"]
    assert len(two) == 2 and all(c.shape == "d" for c in two)
    assert two[0].y < two[1].y and two[0].x == two[1].x  # two holes above each other


def test_cutouts_are_parsed(raw):
    raw["cutout"] = [
        {"name": "D hole", "version": "A", "shape": "d", "x": 18, "y": 30, "diameter": 24, "flat": 10.5, "flat_side": "bottom"},
        {"name": "plain", "version": "A", "shape": "d", "x": 18, "y": 30, "diameter": 24},
        {"name": "Screw", "version": "B", "shape": "circle", "x": 4, "y": 4, "diameter": 3.2},
        {"name": "Slot", "version": "B", "shape": "rect", "x": 10, "y": 30, "width": 17, "height": 12},
    ]
    s = parse_settings(raw)
    assert s.cutout_versions == ("A", "B")
    d, plain, screw, slot = s.cutouts
    assert (d.flat, d.flat_side) == (10.5, "bottom") and plain.flat == 0.0
    assert (screw.shape, screw.diameter) == ("circle", 3.2)
    assert (slot.width, slot.height) == (17.0, 12.0)


def test_cutouts_from_toml_text():
    toml = (ROOT / "config.toml").read_text() + '\n[[cutout]]\nname = "x"\nversion = "2xD"\nshape = "circle"\nx = 1\ny = 2\ndiameter = 3\n'
    assert parse_settings(tomllib.loads(toml)).cutout_versions == ("1xD", "2xD")


def test_no_cutouts_at_all_is_fine(raw):
    raw.pop("cutout", None)
    s = parse_settings(raw)
    assert s.cutouts == () and s.cutout_versions == ()


@pytest.mark.parametrize(
    "entry,message",
    [
        ({"version": "A", "shape": "rect", "x": 1, "y": 1, "width": 1, "height": 1}, "needs a name"),
        ({"name": "z", "shape": "circle", "x": 1, "y": 1, "diameter": 3}, "needs a version"),
        ({"name": "z", "version": "A", "shape": "star", "x": 1, "y": 1}, "shape must be"),
        ({"name": "z", "version": "A", "shape": "rect", "x": 1, "y": 1, "width": 5}, "missing key height"),
        ({"name": "z", "version": "A", "shape": "circle", "x": 1, "y": 1, "diameter": 0}, "diameter must be > 0"),
        ({"name": "z", "version": "A", "shape": "circle", "x": 1, "y": 1, "diameter": 3, "flat": 1}, "unknown key flat"),
        ({"name": "z", "version": "A", "shape": "circle", "x": "left", "y": 1, "diameter": 3}, "must be a number"),
        ({"name": "z", "version": "A", "shape": "d", "x": 1, "y": 1, "diameter": 24, "flat": 5}, "belong together"),
        ({"name": "z", "version": "A", "shape": "d", "x": 1, "y": 1, "diameter": 24, "flat_side": "top"}, "belong together"),
        ({"name": "z", "version": "A", "shape": "d", "x": 1, "y": 1, "diameter": 24, "flat": 12, "flat_side": "top"}, "between 0 and the radius"),
        ({"name": "z", "version": "A", "shape": "d", "x": 1, "y": 1, "diameter": 24, "flat": 5, "flat_side": "middle"}, "flat_side must be"),
    ],
)
def test_bad_cutout_entries_are_rejected(raw, entry, message):
    raw["cutout"] = [entry]
    with pytest.raises(ConfigError, match=message):
        parse_settings(raw)


def test_cutouts_written_with_single_brackets_are_rejected(raw):
    raw["cutout"] = {"name": "z"}
    with pytest.raises(ConfigError, match="double brackets"):
        parse_settings(raw)
