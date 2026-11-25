"""The single page: a table with the top and bottom text of every fixture slot, a "Create program"
button, the G-code next to a 2D preview of it, and Save as.

With a one-slot fixture the table has one row, which is the single-cover case. No geometry or
G-code logic lives here; the window only calls create_program_for_slots() and shows the result.
"""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import create_program_for_slots
from ..config import Settings
from ..gcode import to_file_bytes
from ..layout import LayoutError
from .preview_view import PreviewView
from .settings_dialog import SettingsDialog

TOP, BOTTOM = 0, 1  # table columns


class MainWindow(QWidget):
    def __init__(self, settings: Settings, config_path: Path | str | None = None) -> None:
        super().__init__()
        self.settings = settings
        self.config_path = config_path  # the file the Settings dialog writes (None: the project's config.toml)
        self._program = ""
        self.setWindowTitle("ArtisanCAM")
        self.resize(1050, 780)

        self.slot_table = QTableWidget(0, 2)  # one row per fixture slot: top text, bottom text
        self.slot_table.setHorizontalHeaderLabels(["Top text", "Bottom text (optional)"])
        self.slot_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.slot_table.setEditTriggers(QAbstractItemView.EditTrigger.AllEditTriggers)  # just start typing
        self.copy_button = QPushButton("Copy slot 1 to all")
        self.copy_button.setToolTip("Put the texts of slot 1 into every slot")
        self.create_button = QPushButton("Create program")
        self.settings_button = QPushButton("Settings…")
        self.save_button = QPushButton("Save as…")
        self.save_button.setEnabled(False)
        self.status = QLabel("Enter a top and/or bottom text per slot and click Create program.")
        self.status.setWordWrap(True)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.output.setPlaceholderText("The G-code appears here.")
        self.preview = PreviewView(settings)
        self.cutout_select = QComboBox()  # which cover version's holes are drawn in red (display only)
        self.cutout_select.addItems(settings.cutout_versions)
        self.cutout_select.addItem("No cut-outs")
        self.cutout_select.setToolTip("Draws the holes of this cover version in red on the preview. The G-code is not affected.")
        legend = QLabel("Black-white circle: reference point, set X0 Y0 here (Z0 = cover top) · green: engraving · "
                        "dashed grey: travel · red: cut-outs (drawn only) · dashed slot: no text, not engraved · "
                        "wheel zooms, drag pans, double-click fits")
        legend.setWordWrap(True)
        legend.setStyleSheet("color: #5b6670; font-size: 11px;")
        self._set_slot_rows(settings.slot_count)

        layout = QVBoxLayout(self)
        layout.addWidget(self.slot_table)
        form = QFormLayout()
        form.addRow("Cut-outs shown", self.cutout_select)
        layout.addLayout(form)
        buttons = QHBoxLayout()
        buttons.addWidget(self.create_button, stretch=1)
        buttons.addWidget(self.copy_button)
        buttons.addWidget(self.settings_button)
        layout.addLayout(buttons)
        layout.addWidget(self.status)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(legend)
        right_layout.addWidget(self.preview, stretch=1)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.output)  # G-code on the left, preview on the right
        splitter.addWidget(right)
        splitter.setSizes([1, 1])
        layout.addWidget(splitter, stretch=1)
        layout.addWidget(self.save_button)

        self.create_button.clicked.connect(self.on_create_clicked)
        self.copy_button.clicked.connect(self.copy_first_slot_to_all)
        self.slot_table.itemChanged.connect(self._text_changed)
        self.save_button.clicked.connect(self.save)
        self.settings_button.clicked.connect(self.open_settings)
        self.cutout_select.currentIndexChanged.connect(self._cutouts_changed)

    # --- the slot table -----------------------------------------------------------------------------

    def slot_texts(self) -> list[tuple[str, str]]:
        """(top, bottom) for every slot, in slot order."""
        return [(self._cell(row, TOP), self._cell(row, BOTTOM)) for row in range(self.slot_table.rowCount())]

    def set_slot_text(self, slot: int, top: str, bottom: str = "") -> None:
        """Fill one slot (0-based row)."""
        for column, text in ((TOP, top), (BOTTOM, bottom)):
            item = self.slot_table.item(slot, column)
            if item is None:
                self.slot_table.setItem(slot, column, QTableWidgetItem(text))
            else:
                item.setText(text)

    def copy_first_slot_to_all(self) -> None:
        top, bottom = self.slot_texts()[0]
        for row in range(1, self.slot_table.rowCount()):
            self.set_slot_text(row, top, bottom)

    def _cell(self, row: int, column: int) -> str:
        item = self.slot_table.item(row, column)
        return item.text() if item is not None else ""

    def _set_slot_rows(self, count: int) -> list[int]:
        """Make the table have `count` rows, keeping the texts that still fit. Returns the numbers of
        removed slots that had text."""
        old = self.slot_texts()
        lost = [n for n, (top, bottom) in enumerate(old[count:], count + 1) if top.strip() or bottom.strip()]
        self.slot_table.blockSignals(True)  # filling cells must not count as "text changed"
        self.slot_table.setRowCount(count)
        for row in range(count):
            top, bottom = old[row] if row < len(old) else ("", "")
            self.slot_table.setItem(row, TOP, QTableWidgetItem(top))
            self.slot_table.setItem(row, BOTTOM, QTableWidgetItem(bottom))
        self.slot_table.setVerticalHeaderLabels([f"Slot {n}" for n in range(1, count + 1)])
        self.slot_table.blockSignals(False)
        self.copy_button.setVisible(count > 1)
        # Show every row without scrolling (header + rows + frame).
        height = self.slot_table.horizontalHeader().height() + sum(self.slot_table.rowHeight(r) for r in range(count))
        self.slot_table.setFixedHeight(height + 2 * self.slot_table.frameWidth() + 2)
        self._update_slot_states()
        return lost

    def _update_slot_states(self) -> None:
        self.preview.set_slot_states([bool(top.strip() or bottom.strip()) for top, bottom in self.slot_texts()])

    # --- actions ------------------------------------------------------------------------------------------

    def on_create_clicked(self) -> None:
        slots = self.slot_texts()
        try:
            program = create_program_for_slots(slots, self.settings)
        except LayoutError as exc:
            self.output.clear()
            self.preview.clear_program()
            self.save_button.setEnabled(False)
            self.status.setText(f"Error: {exc}")
            return
        self._program = program
        self.output.setPlainText(program)
        self.save_button.setEnabled(True)
        parsed = self.preview.show_program(program)
        filled = [" / ".join(t.strip() for t in pair if t.strip()) for pair in slots]
        filled = [text for text in filled if text]
        if self.settings.slot_count == 1:
            what = f"“{filled[0]}”"
        else:
            what = f"{len(filled)} of {self.settings.slot_count} slots"
        self.status.setText(
            f"Program created for {what}: {parsed.strokes} strokes, {parsed.cut_length:.1f} mm engraved. "
            "Check the preview, then save."
        )

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self.config_path, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.saved_settings is not None:
            self.apply_settings(dialog.saved_settings)

    def apply_settings(self, settings: Settings) -> None:
        """Use new settings at once: redraw the preview, the slot table and the cut-out list. A program
        already shown was made with the old values, so it is faded and cannot be saved until it is
        created again."""
        self.settings = settings
        self.preview.set_settings(settings)  # keeps the chosen cut-out version if it still exists
        lost = self._set_slot_rows(settings.slot_count)
        version = self.preview.cutout_version
        self.cutout_select.blockSignals(True)  # rebuilding the list must not trigger redraws
        self.cutout_select.clear()
        self.cutout_select.addItems(settings.cutout_versions)
        self.cutout_select.addItem("No cut-outs")
        versions = settings.cutout_versions
        self.cutout_select.setCurrentIndex(versions.index(version) if version in versions else len(versions))
        self.cutout_select.blockSignals(False)
        message = "Settings saved."
        if lost:
            message += f" The fixture has fewer slots now; the text of slot {', '.join(map(str, lost))} was dropped."
        if self.output.toPlainText():
            self.preview.show_program(self._program)
            self.preview.set_stale(True)
            self.save_button.setEnabled(False)
            message += " Click Create program to make the G-code with the new values."
        self.status.setText(message)

    def _cutouts_changed(self) -> None:
        # The last entry is "No cut-outs"; the others are the version names from the config.
        versions = self.settings.cutout_versions
        index = self.cutout_select.currentIndex()
        self.preview.set_cutout_version(versions[index] if index < len(versions) else None)

    def _text_changed(self) -> None:
        self._update_slot_states()
        # The shown program belongs to the previous text; never leave it saveable.
        if self.save_button.isEnabled():
            self.save_button.setEnabled(False)
            self.preview.set_stale(True)
            self.status.setText("Text changed. Click Create program to update the G-code.")

    def save(self) -> None:
        names = " ".join(top or bottom for top, bottom in self.slot_texts() if top.strip() or bottom.strip())
        stem = re.sub(r"[^A-Za-z0-9_-]+", "_", names).strip("_")[:60].strip("_") or "engraving"
        path, _ = QFileDialog.getSaveFileName(self, "Save G-code", str(Path.home() / f"{stem}.cnc"), "Snapmaker CNC (*.cnc)")
        if not path:
            return
        try:
            Path(path).write_bytes(to_file_bytes(self._program))
        except OSError as exc:
            self.status.setText(f"Could not save: {exc}")
            return
        self.status.setText(f"Saved {path}")
