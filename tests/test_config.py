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
