import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # the window test needs no display

from artisancam.config import load_settings  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "reference" / "HDMI_OUT_v4.cnc"  # gitignored; tests that need it skip when absent


@pytest.fixture
def settings():
    return load_settings(ROOT / "config.toml")


@pytest.fixture(scope="session")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])
