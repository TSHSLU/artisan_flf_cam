import pytest

PySide6 = pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from artisancam.ui.window import MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, settings):
    w = MainWindow(settings)
    yield w
    w.close()


def test_create_shows_a_program_and_enables_save(window):
    window.text_input.setText("HDMI-OUT")
    window.create_button.click()
    assert "M3 P100" in window.output.toPlainText()
    assert window.save_button.isEnabled()


def test_error_is_shown_and_nothing_is_saveable(window):
    window.text_input.setText("HDMI-OUT HDMI-OUT")
    window.create_button.click()
    assert window.status.text().startswith("Error:")
    assert window.output.toPlainText() == ""
    assert not window.save_button.isEnabled()


def test_editing_the_text_invalidates_the_shown_program(window):
    window.text_input.setText("A")
    window.create_button.click()
    assert window.save_button.isEnabled()
    window.text_input.setText("AB")
    assert not window.save_button.isEnabled()


def test_enter_key_creates_the_program(window):
    window.text_input.setText("Öl")
    window.text_input.returnPressed.emit()
    assert window.save_button.isEnabled()
