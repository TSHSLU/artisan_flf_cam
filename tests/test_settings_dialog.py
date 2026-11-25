"""The Settings dialog. It always works on copies of the config files in a temporary folder."""

import shutil

import pytest

from artisancam.config import FIELDS, load_settings, save_settings, values_of
from conftest import ROOT


@pytest.fixture
def paths(tmp_path):
    config = tmp_path / "config.toml"
    defaults = tmp_path / "config.defaults.toml"
    shutil.copyfile(ROOT / "config.toml", config)
    shutil.copyfile(ROOT / "config.defaults.toml", defaults)
    return config, defaults


@pytest.fixture
def dialog(qapp, paths):
    from artisancam.ui.settings_dialog import SettingsDialog

    config, defaults = paths
    d = SettingsDialog(load_settings(config), config_path=config, defaults_path=defaults)
    yield d
    d.close()


def test_one_box_per_setting_showing_the_current_value(dialog, paths):
    current = values_of(load_settings(paths[0]))
    assert set(dialog.boxes) == {f.field for f in FIELDS}
    for field, value in current.items():
        assert dialog.boxes[field].value() == pytest.approx(value)


def test_two_tabs_and_machine_values_on_the_machine_tab(dialog):
    assert [dialog.tabs.tabText(i) for i in range(dialog.tabs.count())] == ["Cover and text", "Machine"]
    layout_page, machine_page = dialog.tabs.widget(0), dialog.tabs.widget(1)
    for spec in FIELDS:
        page = machine_page if spec.tab == "machine" else layout_page
        assert page.isAncestorOf(dialog.boxes[spec.field]), spec.field


def test_machine_tab_shows_a_warning(dialog):
    from PySide6.QtWidgets import QLabel

    texts = [label.text() for label in dialog.tabs.widget(1).findChildren(QLabel)]
    assert any("known-good" in t for t in texts)


def test_numbers_use_a_decimal_point_and_units(dialog):
    box = dialog.boxes["depth"]
    assert box.textFromValue(0.2) == "0.200"
    assert box.suffix() == " mm"
    assert dialog.boxes["cutting_feed"].suffix() == " mm/min"


def test_save_writes_the_file_and_closes(dialog, paths):
    from PySide6.QtWidgets import QDialog

    dialog.boxes["depth"].setValue(0.25)
    dialog.save()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.saved_settings is not None and dialog.saved_settings.depth == 0.25
    assert load_settings(paths[0]).depth == 0.25


def test_invalid_values_are_refused_and_the_dialog_stays_open(dialog, paths):
    from PySide6.QtWidgets import QDialog

    before = paths[0].read_bytes()
    dialog.boxes["spindle_percent"].setValue(40)
    dialog.save()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog.saved_settings is None
    assert dialog.message.text().startswith("Not saved:") and "above 50" in dialog.message.text()
    assert paths[0].read_bytes() == before


def test_restore_defaults_fills_in_but_does_not_write(dialog, paths):
    config, defaults = paths
    # Give the defaults file a different depth so the restore is visible.
    values = values_of(load_settings(defaults))
    values["depth"] = 0.3
    save_settings(values, defaults)
    before = config.read_bytes()

    dialog.boxes["depth"].setValue(0.5)
    dialog.restore_defaults()
    assert dialog.boxes["depth"].value() == pytest.approx(0.3)
    assert "Default values filled in" in dialog.message.text()
    assert config.read_bytes() == before  # nothing written until Save


def test_restore_then_save_writes_the_defaults(dialog, paths):
    config, defaults = paths
    values = values_of(load_settings(config))
    values["cutting_feed"] = 1234.0
    save_settings(values, config)  # the working file drifted away from the defaults
    from artisancam.ui.settings_dialog import SettingsDialog

    d = SettingsDialog(load_settings(config), config_path=config, defaults_path=defaults)
    d.restore_defaults()
    d.save()
    assert values_of(load_settings(config)) == values_of(load_settings(defaults))
    d.close()


def test_unreadable_defaults_show_an_error(qapp, paths, tmp_path):
    from artisancam.ui.settings_dialog import SettingsDialog

    config, _ = paths
    d = SettingsDialog(load_settings(config), config_path=config, defaults_path=tmp_path / "missing.toml")
    depth = d.boxes["depth"].value()
    d.restore_defaults()
    assert d.message.text().startswith("Not saved: Cannot read the defaults")
    assert d.boxes["depth"].value() == depth  # nothing changed
    d.close()
