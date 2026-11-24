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
    assert settings.stock_width == 37.25 and settings.stock_length == 63.0
    assert settings.depth == 0.2
    assert settings.spindle_percent == 100


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
    assert (settings.top_height, settings.top_margin) == (3.5, 4.0)
    assert (settings.bottom_height, settings.bottom_margin) == (3.5, 4.0)
    assert settings.keepout_clearance == 1.0


def test_missing_bottom_key_is_named(raw):
    del raw["text_bottom"]["margin"]
    with pytest.raises(ConfigError, match=r"\[text_bottom\] margin"):
        parse_settings(raw)


def test_keepout_zones_are_parsed(raw):
    raw["keepout"] = [
        {"name": "D-cut", "shape": "rect", "x": 10, "y": 30, "width": 17, "height": 12},
        {"name": "Screw hole 1", "shape": "circle", "x": 4, "y": 4, "diameter": 3.2},
    ]
    zones = parse_settings(raw).keepouts
    assert [z.name for z in zones] == ["D-cut", "Screw hole 1"]
    assert (zones[0].shape, zones[0].width, zones[0].height) == ("rect", 17.0, 12.0)
    assert (zones[1].shape, zones[1].diameter) == ("circle", 3.2)


def test_keepout_from_toml_text(raw):
    toml = (ROOT / "config.toml").read_text() + '\n[[keepout]]\nname = "hole"\nshape = "circle"\nx = 1\ny = 2\ndiameter = 3\n'
    zones = parse_settings(tomllib.loads(toml)).keepouts
    assert len(zones) == 1 and zones[0].name == "hole"


@pytest.mark.parametrize(
    "entry,message",
    [
        ({"shape": "rect", "x": 1, "y": 1, "width": 1, "height": 1}, "needs a name"),
        ({"name": "z", "shape": "star", "x": 1, "y": 1}, "shape must be"),
        ({"name": "z", "shape": "rect", "x": 1, "y": 1, "width": 5}, "missing key height"),
        ({"name": "z", "shape": "circle", "x": 1, "y": 1, "diameter": 0}, "diameter must be > 0"),
        ({"name": "z", "shape": "circle", "x": 1, "y": 1, "diameter": 3, "width": 2}, "unknown key width"),
        ({"name": "z", "shape": "circle", "x": "left", "y": 1, "diameter": 3}, "must be a number"),
    ],
)
def test_bad_keepout_entries_are_rejected(raw, entry, message):
    raw["keepout"] = [entry]
    with pytest.raises(ConfigError, match=message):
        parse_settings(raw)


def test_keepout_written_with_single_brackets_is_rejected(raw):
    raw["keepout"] = {"name": "z"}
    with pytest.raises(ConfigError, match="double brackets"):
        parse_settings(raw)
