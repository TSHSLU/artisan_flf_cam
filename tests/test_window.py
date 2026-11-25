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
    window.set_slot_text(0, "HDMI-OUT")
    window.create_button.click()
    assert "M3 P100" in window.output.toPlainText()
    assert window.save_button.isEnabled()


def test_error_is_shown_and_nothing_is_saveable(window):
    window.set_slot_text(0, "HDMI-OUT HDMI-OUT")
    window.create_button.click()
    assert window.status.text().startswith("Error:")
    assert window.output.toPlainText() == ""
    assert not window.save_button.isEnabled()


def test_editing_the_text_invalidates_the_shown_program(window):
    window.set_slot_text(0, "A")
    window.create_button.click()
    assert window.save_button.isEnabled()
    window.set_slot_text(0, "AB")
    assert not window.save_button.isEnabled()


def test_umlauts_in_the_table_create_a_program(window):
    window.set_slot_text(0, "Öl")
    window.create_button.click()
    assert window.save_button.isEnabled()


def test_bottom_text_alone_creates_a_program(window, settings):
    window.set_slot_text(0, "", "HDMI IN")
    window.create_button.click()
    assert window.save_button.isEnabled()
    assert "HDMI IN" in window.status.text()
    ys = [float(t.split("Y")[1].split()[0]) for t in window.output.toPlainText().splitlines() if t.startswith("G1")]
    assert ys and max(ys) < -settings.stock_length / 2  # everything lies in the lower half: only the bottom line


def test_both_texts_are_used(window, settings):
    window.set_slot_text(0, "HDMI", "HDMI")
    window.create_button.click()
    ys = [float(t.split("Y")[1].split()[0]) for t in window.output.toPlainText().splitlines() if t.startswith("G1")]
    assert max(ys) > -10 and min(ys) < -settings.stock_length + 10


def test_an_empty_table_shows_an_error(window):
    window.create_button.click()
    assert window.status.text().startswith("Error:")
    assert not window.save_button.isEnabled()


def test_editing_the_bottom_text_invalidates_the_shown_program(window):
    window.set_slot_text(0, "A")
    window.create_button.click()
    assert window.save_button.isEnabled()
    window.set_slot_text(0, "A", "B")
    assert not window.save_button.isEnabled()


def test_error_names_the_bottom_line(window):
    window.set_slot_text(0, "HDMI", "HDMI-OUT HDMI-OUT")
    window.create_button.click()
    assert "Bottom text" in window.status.text()


# --- G-code and preview side by side ------------------------------------------------------------------


def test_preview_shows_the_created_program(window):
    window.set_slot_text(0, "HDMI OUT")
    window.create_button.click()
    assert window.preview.drawn_cut_moves > 0
    assert not window.preview.stale
    assert "strokes" in window.status.text() and "mm engraved" in window.status.text()


def test_an_error_clears_the_preview(window):
    window.set_slot_text(0, "HDMI")
    window.create_button.click()
    assert window.preview.drawn_cut_moves > 0
    window.set_slot_text(0, "HDMI-OUT HDMI-OUT")
    window.create_button.click()
    assert window.preview.drawn_cut_moves == 0


def test_editing_the_text_fades_the_preview(window):
    window.set_slot_text(0, "A")
    window.create_button.click()
    window.set_slot_text(0, "AB")
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
    window.set_slot_text(0, "HDMI OUT")
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

    window.set_slot_text(0, "HDMI")
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


# --- several covers: the slot table -------------------------------------------------------------------------


@pytest.fixture
def window6(app, six_slots):
    w = MainWindow(six_slots)
    yield w
    w.close()


def _ys(program):
    return [float(t.split("Y")[1].split()[0]) for t in program.splitlines() if t.startswith("G1")]


def _xs(program):
    return [float(t.split("X")[1].split()[0]) for t in program.splitlines() if t.startswith("G1")]


def test_single_slot_fixture_has_one_row_and_no_copy_button(window):
    assert window.slot_table.rowCount() == 1
    assert window.copy_button.isHidden()


def test_one_table_row_per_slot(window6):
    assert window6.slot_table.rowCount() == 6
    labels = [window6.slot_table.verticalHeaderItem(r).text() for r in range(6)]
    assert labels == [f"Slot {n}" for n in range(1, 7)]
    assert not window6.copy_button.isHidden()


def test_all_six_slots_are_engraved_where_they_belong(window6, six_slots):
    for slot in range(6):
        window6.set_slot_text(slot, f"S{slot + 1}")
    window6.create_button.click()
    program = window6.output.toPlainText()
    assert window6.save_button.isEnabled()
    assert "6 of 6 slots" in window6.status.text()
    for n in range(1, 7):
        assert f";Slot {n}: S{n}" in program
    xs, ys = _xs(program), _ys(program)
    # Text in all three columns and both rows.
    assert min(xs) < six_slots.stock_width and max(xs) > 2 * six_slots.pitch_x
    assert max(ys) > -10 and min(ys) < -(six_slots.pitch_y + 2)


def test_empty_slots_are_skipped_and_drawn_dashed(window6):
    window6.set_slot_text(0, "A")
    window6.set_slot_text(4, "B")
    assert window6.preview.filled_slots == (True, False, False, False, True, False)
    window6.create_button.click()
    program = window6.output.toPlainText()
    assert ";Slot 1: A" in program and ";Slot 5: B" in program and ";Slot 2:" not in program
    assert "2 of 6 slots" in window6.status.text()


def test_copy_slot_1_to_all(window6):
    window6.set_slot_text(0, "HDMI OUT", "Rückseite")
    window6.copy_button.click()
    assert window6.slot_texts() == [("HDMI OUT", "Rückseite")] * 6
    assert window6.preview.filled_slots == (True,) * 6


def test_editing_any_slot_makes_the_program_stale(window6):
    window6.set_slot_text(0, "A")
    window6.create_button.click()
    assert window6.save_button.isEnabled()
    window6.set_slot_text(5, "late")
    assert not window6.save_button.isEnabled() and window6.preview.stale


def test_error_names_the_slot(window6):
    window6.set_slot_text(0, "ok")
    window6.set_slot_text(3, "", "HDMI-OUT HDMI-OUT")
    window6.create_button.click()
    assert window6.status.text().startswith("Error: Slot 4: Bottom text:")
    assert not window6.save_button.isEnabled()


def test_preview_draws_every_slot_and_all_engravings(window6):
    window6.set_slot_text(0, "HDMI")
    window6.copy_button.click()
    window6.create_button.click()
    preview = window6.preview
    assert preview.slot_count == 6
    one = MainWindow(__import__("dataclasses").replace(window6.settings, fixture_columns=1, fixture_rows=1))
    one.set_slot_text(0, "HDMI")
    one.create_button.click()
    assert preview.drawn_cut_moves == 6 * one.preview.drawn_cut_moves  # the same text drawn in every slot
    one.close()


def test_fewer_slots_keep_the_first_texts_and_say_what_was_dropped(window6, six_slots):
    import dataclasses

    for slot in range(6):
        window6.set_slot_text(slot, f"S{slot + 1}")
    window6.apply_settings(dataclasses.replace(six_slots, fixture_columns=3, fixture_rows=1))
    assert window6.slot_texts() == [("S1", ""), ("S2", ""), ("S3", "")]
    assert window6.preview.slot_count == 3
    assert "slot 4, 5, 6" in window6.status.text()


def test_more_slots_add_empty_rows(window, settings):
    import dataclasses

    window.set_slot_text(0, "keep")
    window.apply_settings(dataclasses.replace(settings, fixture_columns=2, fixture_rows=1, pitch_x=45.0))
    assert window.slot_texts() == [("keep", ""), ("", "")]
    assert not window.copy_button.isHidden()
