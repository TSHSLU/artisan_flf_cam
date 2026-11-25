"""The single page: top and bottom text fields, a "Create program" button, the G-code next to a
2D preview of it, and Save as.

No geometry or G-code logic lives here; the window only calls create_program() and shows the result.
"""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QFileDialog,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .. import create_program
from ..config import Settings
from ..gcode import to_file_bytes
from ..layout import LayoutError
from .preview_view import PreviewView
from .settings_dialog import SettingsDialog


class MainWindow(QWidget):
    def __init__(self, settings: Settings, config_path: Path | str | None = None) -> None:
        super().__init__()
        self.settings = settings
        self.config_path = config_path  # the file the Settings dialog writes (None: the project's config.toml)
        self._program = ""
        self.setWindowTitle("ArtisanCAM")
        self.resize(1050, 720)

        self.text_input = QLineEdit()  # top line
        self.text_input.setPlaceholderText("Text near the top edge, e.g. HDMI OUT")
        self.bottom_input = QLineEdit()
        self.bottom_input.setPlaceholderText("Optional: text near the bottom edge")
        self.create_button = QPushButton("Create program")
        self.settings_button = QPushButton("Settings…")
        self.save_button = QPushButton("Save as…")
        self.save_button.setEnabled(False)
        self.status = QLabel("Enter a top and/or bottom text and click Create program.")
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
        legend = QLabel("Green: engraving · dashed grey: travel · red: cut-outs (drawn only, cut separately) · "
                        "wheel zooms, drag pans, double-click fits")
        legend.setWordWrap(True)
        legend.setStyleSheet("color: #5b6670; font-size: 11px;")

        form = QFormLayout()
        form.addRow("Top text", self.text_input)
        form.addRow("Bottom text", self.bottom_input)
        form.addRow("Cut-outs shown", self.cutout_select)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        buttons = QHBoxLayout()
        buttons.addWidget(self.create_button, stretch=1)
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
        for field in (self.text_input, self.bottom_input):
            field.returnPressed.connect(self.on_create_clicked)
            field.textChanged.connect(self._text_changed)
        self.save_button.clicked.connect(self.save)
        self.settings_button.clicked.connect(self.open_settings)
        self.cutout_select.currentIndexChanged.connect(self._cutouts_changed)

    def on_create_clicked(self) -> None:
        top, bottom = self.text_input.text(), self.bottom_input.text()
        try:
            program = create_program(top, self.settings, bottom=bottom)
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
        shown = " / ".join(t.strip() for t in (top, bottom) if t.strip())
        self.status.setText(
            f"Program created for “{shown}”: {parsed.strokes} strokes, {parsed.cut_length:.1f} mm engraved. "
            "Check the preview, then save."
        )

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self.config_path, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.saved_settings is not None:
            self.apply_settings(dialog.saved_settings)

    def apply_settings(self, settings: Settings) -> None:
        """Use new settings at once: redraw the preview and the cut-out list. A program already shown was
        made with the old values, so it is faded and cannot be saved until it is created again."""
        self.settings = settings
        self.preview.set_settings(settings)  # keeps the chosen cut-out version if it still exists
        version = self.preview.cutout_version
        self.cutout_select.blockSignals(True)  # rebuilding the list must not trigger redraws
        self.cutout_select.clear()
        self.cutout_select.addItems(settings.cutout_versions)
        self.cutout_select.addItem("No cut-outs")
        versions = settings.cutout_versions
        self.cutout_select.setCurrentIndex(versions.index(version) if version in versions else len(versions))
        self.cutout_select.blockSignals(False)
        if self.output.toPlainText():
            self.preview.show_program(self._program)
            self.preview.set_stale(True)
            self.save_button.setEnabled(False)
            self.status.setText("Settings saved. Click Create program to make the G-code with the new values.")
        else:
            self.status.setText("Settings saved.")

    def _cutouts_changed(self) -> None:
        # The last entry is "No cut-outs"; the others are the version names from the config.
        versions = self.settings.cutout_versions
        index = self.cutout_select.currentIndex()
        self.preview.set_cutout_version(versions[index] if index < len(versions) else None)

    def _text_changed(self) -> None:
        # The shown program belongs to the previous text; never leave it saveable.
        if self.save_button.isEnabled():
            self.save_button.setEnabled(False)
            self.preview.set_stale(True)
            self.status.setText("Text changed. Click Create program to update the G-code.")

    def save(self) -> None:
        names = f"{self.text_input.text()} {self.bottom_input.text()}"
        stem = re.sub(r"[^A-Za-z0-9_-]+", "_", names).strip("_") or "engraving"
        path, _ = QFileDialog.getSaveFileName(self, "Save G-code", str(Path.home() / f"{stem}.cnc"), "Snapmaker CNC (*.cnc)")
        if not path:
            return
        try:
            Path(path).write_bytes(to_file_bytes(self._program))
        except OSError as exc:
            self.status.setText(f"Could not save: {exc}")
            return
        self.status.setText(f"Saved {path}")
