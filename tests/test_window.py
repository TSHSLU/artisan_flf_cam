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


def test_bottom_text_alone_creates_a_program(window, settings):
    window.bottom_input.setText("HDMI IN")
    window.create_button.click()
    assert window.save_button.isEnabled()
    assert "HDMI IN" in window.status.text()
    ys = [float(t.split("Y")[1].split()[0]) for t in window.output.toPlainText().splitlines() if t.startswith("G1")]
    assert ys and max(ys) < -settings.stock_length / 2  # everything lies in the lower half: only the bottom line


def test_both_texts_are_used(window, settings):
    window.text_input.setText("HDMI")
    window.bottom_input.setText("HDMI")
    window.create_button.click()
    ys = [float(t.split("Y")[1].split()[0]) for t in window.output.toPlainText().splitlines() if t.startswith("G1")]
    assert max(ys) > -10 and min(ys) < -settings.stock_length + 10


def test_both_fields_empty_shows_an_error(window):
    window.create_button.click()
    assert window.status.text().startswith("Error:")
    assert not window.save_button.isEnabled()


def test_editing_the_bottom_text_invalidates_the_shown_program(window):
    window.text_input.setText("A")
    window.create_button.click()
    assert window.save_button.isEnabled()
    window.bottom_input.setText("B")
    assert not window.save_button.isEnabled()


def test_error_names_the_bottom_line(window):
    window.text_input.setText("HDMI")
    window.bottom_input.setText("HDMI-OUT HDMI-OUT")
    window.create_button.click()
    assert "Bottom text" in window.status.text()


# --- G-code and preview side by side ------------------------------------------------------------------


def test_preview_shows_the_created_program(window):
    window.text_input.setText("HDMI OUT")
    window.create_button.click()
    assert window.preview.drawn_cut_moves > 0
    assert not window.preview.stale
    assert "strokes" in window.status.text() and "mm engraved" in window.status.text()


def test_an_error_clears_the_preview(window):
    window.text_input.setText("HDMI")
    window.create_button.click()
    assert window.preview.drawn_cut_moves > 0
    window.text_input.setText("HDMI-OUT HDMI-OUT")
    window.create_button.click()
    assert window.preview.drawn_cut_moves == 0


def test_editing_the_text_fades_the_preview(window):
    window.text_input.setText("A")
    window.create_button.click()
    window.text_input.setText("AB")
    assert window.preview.stale
    window.create_button.click()
    assert not window.preview.stale


def test_gcode_and_preview_are_side_by_side(app, window):
    from PySide6.QtCore import QPoint

    window.show()
    app.processEvents()
    gcode_left = window.output.mapTo(window, QPoint(0, 0))
    preview_left = window.preview.mapTo(window, QPoint(0, 0))
    assert gcode_left.x() + window.output.width() <= preview_left.x() + 2  # preview starts right of the G-code
    assert abs(window.output.height() - window.preview.height()) < 80  # similar height: next to each other


# --- cut-out dropdown (display only) -----------------------------------------------------------------


def test_dropdown_lists_the_config_versions_and_a_no_cutouts_entry(window, settings):
    items = [window.cutout_select.itemText(i) for i in range(window.cutout_select.count())]
    assert items == [*settings.cutout_versions, "No cut-outs"]
    assert window.preview.cutout_version == settings.cutout_versions[0]  # the first version is shown at start


def test_choosing_no_cutouts_hides_the_red_shapes_and_back(window, settings):
    window.cutout_select.setCurrentIndex(window.cutout_select.count() - 1)
    assert window.preview.cutout_version is None and window.preview.drawn_cutouts == 0
    window.cutout_select.setCurrentIndex(0)
    assert window.preview.cutout_version == settings.cutout_versions[0]
    assert window.preview.drawn_cutouts == sum(1 for c in settings.cutouts if c.version == settings.cutout_versions[0])


def test_choosing_2xd_draws_two_holes_and_not_the_1xd_shapes(window, settings):
    window.cutout_select.setCurrentText("2xD")
    assert window.preview.cutout_version == "2xD"
    assert window.preview.drawn_cutouts == 2  # two D holes, no screw holes
    window.cutout_select.setCurrentText("1xD")
    assert window.preview.drawn_cutouts == 3  # D hole + two screw holes


def test_the_dropdown_never_changes_the_gcode(window):
    window.text_input.setText("HDMI OUT")
    window.create_button.click()
    before = window.output.toPlainText()
    window.cutout_select.setCurrentIndex(window.cutout_select.count() - 1)
    assert window.output.toPlainText() == before
    assert window.save_button.isEnabled()  # the program is still valid and saveable
    assert not window.preview.stale


# --- settings button and live refresh ---------------------------------------------------------------------


def test_settings_button_exists(window):
    assert window.settings_button.text().startswith("Settings")


def test_new_settings_redraw_the_preview_at_once(window, settings):
    import dataclasses

    longer = dataclasses.replace(settings, stock_length=settings.stock_length + 10)
    window.apply_settings(longer)
    assert window.settings is longer
    assert window.preview.sceneRect().height() == pytest.approx(longer.stock_length + 6)  # 3 mm padding each side
    assert window.status.text() == "Settings saved."


def test_new_settings_make_a_shown_program_stale(window, settings):
    import dataclasses

    window.text_input.setText("HDMI")
    window.create_button.click()
    assert window.save_button.isEnabled()
    window.apply_settings(dataclasses.replace(settings, depth=0.3))
    assert not window.save_button.isEnabled()
    assert window.preview.stale and window.preview.drawn_cut_moves > 0  # old program still visible, faded
    assert "Create program" in window.status.text()
    window.create_button.click()
    assert "Z-0.300" in window.output.toPlainText()  # the new program uses the new depth


def test_chosen_cutout_version_survives_a_settings_change(window, settings):
    import dataclasses

    window.cutout_select.setCurrentText("2xD")
    window.apply_settings(dataclasses.replace(settings, depth=0.3))
    assert window.cutout_select.currentText() == "2xD"
    assert window.preview.cutout_version == "2xD"


def test_settings_without_cutouts_leave_only_no_cutouts(window, settings):
    import dataclasses

    window.apply_settings(dataclasses.replace(settings, cutouts=()))
    assert [window.cutout_select.itemText(i) for i in range(window.cutout_select.count())] == ["No cut-outs"]
    assert window.preview.cutout_version is None and window.preview.drawn_cutouts == 0
