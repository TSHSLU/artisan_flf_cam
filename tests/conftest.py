import dataclasses
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # the window test needs no display

from artisancam.config import load_settings  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "reference" / "HDMI_OUT_v4.cnc"  # gitignored; tests that need it skip when absent


@pytest.fixture
def settings():
    """The project's config.toml, but with a ONE-slot fixture: most tests are about a single cover
    and must not depend on how many slots the fixture in config.toml has."""
    return dataclasses.replace(load_settings(ROOT / "config.toml"), fixture_columns=1, fixture_rows=1)


@pytest.fixture
def six_slots(settings):
    """A 3 x 2 fixture with fixed pitch, independent of config.toml."""
    return dataclasses.replace(settings, fixture_columns=3, fixture_rows=2, pitch_x=45.0, pitch_y=70.0)


@pytest.fixture(scope="session")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])
