"""Saving settings back to config.toml (config.save_settings) and the factory defaults.

Every test works on a copy of the config in a temporary folder; the real config.toml is never written.
"""

import dataclasses
import shutil

import pytest

from artisancam.config import (
    DEFAULTS_PATH,
    FIELDS,
    ConfigError,
    Settings,
    load_defaults,
    load_settings,
    save_settings,
    values_of,
)
from conftest import ROOT


@pytest.fixture
def config_copy(tmp_path):
    path = tmp_path / "config.toml"
    shutil.copyfile(ROOT / "config.toml", path)
    return path


def test_fields_cover_every_setting_except_cutouts():
    in_table = {f.field for f in FIELDS}
    in_settings = {f.name for f in dataclasses.fields(Settings)} - {"cutouts"}
    assert in_table == in_settings  # so the dialog shows every value of the file


def test_machine_values_are_on_the_machine_tab():
    tab = {f.field: f.tab for f in FIELDS}
    assert set(tab.values()) == {"layout", "fixture", "machine"}
    for field in ("fixture_columns", "fixture_rows", "pitch_x", "pitch_y"):
        assert tab[field] == "fixture"
    for field in ("depth", "clearance_z", "retract_z", "feed_z", "cutting_feed", "plunge_feed", "retract_feed", "spindle_percent"):
        assert tab[field] == "machine"
    for field in ("stock_width", "stock_length", "top_height", "bottom_margin"):
        assert tab[field] == "layout"


def test_save_round_trip(config_copy):
    values = values_of(load_settings(config_copy))
    values["depth"] = 0.25
    saved = save_settings(values, config_copy)
    assert saved.depth == 0.25
    reloaded = load_settings(config_copy)
    assert reloaded == saved
    assert {k: v for k, v in values_of(reloaded).items() if k != "depth"} == {k: v for k, v in values.items() if k != "depth"}


def test_only_the_edited_line_changes(config_copy):
    before = config_copy.read_text(encoding="utf-8").splitlines()
    values = values_of(load_settings(config_copy))
    values["depth"] = 0.25
    save_settings(values, config_copy)
    after = config_copy.read_text(encoding="utf-8").splitlines()
    changed = [(a, b) for a, b in zip(before, after) if a != b]
    assert len(before) == len(after) and len(changed) == 1
    assert changed[0][1].startswith("depth = 0.25") and "# cutting depth below the stock top" in changed[0][1]


def test_comments_and_cutouts_survive_a_save(config_copy):
    old = load_settings(config_copy)
    values = values_of(old)
    values["stock_length"] = 62.0
    save_settings(values, config_copy)
    text = config_copy.read_text(encoding="utf-8")
    assert "# X size of the FLF cover" in text
    assert "# !! Values marked ASSUMED are guesses." in text
    assert load_settings(config_copy).cutouts == old.cutouts


def test_whole_numbers_stay_whole(config_copy):
    values = values_of(load_settings(config_copy))
    values["cutting_feed"] = 1500.0
    save_settings(values, config_copy)
    lines = config_copy.read_text(encoding="utf-8").splitlines()
    assert any(line.startswith("cutting = 1500 ") for line in lines)  # not "1500.0"


def test_an_invalid_value_is_not_written(config_copy):
    before = config_copy.read_bytes()
    values = values_of(load_settings(config_copy))
    values["spindle_percent"] = 40
    with pytest.raises(ConfigError, match="above 50"):
        save_settings(values, config_copy)
    assert config_copy.read_bytes() == before
    assert not (config_copy.parent / "config.toml.bak").exists()


def test_inconsistent_heights_are_not_written(config_copy):
    before = config_copy.read_bytes()
    values = values_of(load_settings(config_copy))
    values["retract_z"] = 20.0  # above clearance
    with pytest.raises(ConfigError, match="clearance >= retract >= feed"):
        save_settings(values, config_copy)
    assert config_copy.read_bytes() == before


def test_the_previous_file_is_kept_as_bak(config_copy):
    before = config_copy.read_bytes()
    values = values_of(load_settings(config_copy))
    values["depth"] = 0.3
    save_settings(values, config_copy)
    assert (config_copy.parent / "config.toml.bak").read_bytes() == before
    assert not (config_copy.parent / "config.toml.tmp").exists()


def test_saving_unchanged_values_writes_nothing(config_copy):
    before = config_copy.read_bytes()
    save_settings(values_of(load_settings(config_copy)), config_copy)
    assert config_copy.read_bytes() == before
    assert not (config_copy.parent / "config.toml.bak").exists()


def test_windows_line_endings_are_kept(config_copy):
    crlf = config_copy.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\n", "\r\n")
    config_copy.write_bytes(crlf.encode("utf-8"))
    values = values_of(load_settings(config_copy))
    values["depth"] = 0.25
    save_settings(values, config_copy)
    data = config_copy.read_bytes()
    assert b"\r\n" in data and b"\n" not in data.replace(b"\r\n", b"")


def test_unknown_field_is_a_programming_error(config_copy):
    with pytest.raises(ValueError, match="Not a settings field"):
        save_settings({"spindel": 100}, config_copy)


def test_missing_file_is_reported(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        save_settings({"depth": 0.2}, tmp_path / "nope.toml")


def test_defaults_file_exists_and_is_valid():
    assert DEFAULTS_PATH.exists()
    defaults = load_defaults()
    assert set(values_of(defaults)) == {f.field for f in FIELDS}
    assert "FACTORY DEFAULTS" in DEFAULTS_PATH.read_text(encoding="utf-8")
