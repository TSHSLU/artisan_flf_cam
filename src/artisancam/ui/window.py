"""The single page: a text field, a "Create program" button, the G-code, and Save as.

No geometry or G-code logic lives here; the window only calls create_program().
"""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import create_program
from ..config import Settings
from ..gcode import to_file_bytes
from ..layout import LayoutError


class MainWindow(QWidget):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        self._program = ""
        self.setWindowTitle("ArtisanCAM")
        self.resize(720, 640)

        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText("Text to engrave, e.g. HDMI-OUT")
        self.create_button = QPushButton("Create program")
        self.save_button = QPushButton("Save as…")
        self.save_button.setEnabled(False)
        self.status = QLabel("Enter a text and click Create program.")
        self.status.setWordWrap(True)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.output.setPlaceholderText("The G-code appears here.")

        row = QHBoxLayout()
        row.addWidget(self.text_input, stretch=1)
        row.addWidget(self.create_button)
        layout = QVBoxLayout(self)
        layout.addLayout(row)
        layout.addWidget(self.status)
        layout.addWidget(self.output, stretch=1)
        layout.addWidget(self.save_button)

        self.create_button.clicked.connect(self.create)
        self.text_input.returnPressed.connect(self.create)
        self.text_input.textChanged.connect(self._text_changed)
        self.save_button.clicked.connect(self.save)

    def create(self) -> None:
        text = self.text_input.text()
        try:
            program = create_program(text, self.settings)
        except LayoutError as exc:
            self.output.clear()
            self.save_button.setEnabled(False)
            self.status.setText(f"Error: {exc}")
            return
        self._program = program
        self.output.setPlainText(program)
        self.save_button.setEnabled(True)
        moves = sum(1 for line in program.splitlines() if line.startswith("G1"))
        self.status.setText(f"Program created for “{text}”: {moves} cutting moves. Review it, then save.")

    def _text_changed(self) -> None:
        # The shown program belongs to the previous text; never leave it saveable.
        if self.save_button.isEnabled():
            self.save_button.setEnabled(False)
            self.status.setText("Text changed. Click Create program to update the G-code.")

    def save(self) -> None:
        stem = re.sub(r"[^A-Za-z0-9_-]+", "_", self.text_input.text()).strip("_") or "engraving"
        path, _ = QFileDialog.getSaveFileName(self, "Save G-code", str(Path.home() / f"{stem}.cnc"), "Snapmaker CNC (*.cnc)")
        if not path:
            return
        try:
            Path(path).write_bytes(to_file_bytes(self._program))
        except OSError as exc:
            self.status.setText(f"Could not save: {exc}")
            return
        self.status.setText(f"Saved {path}")
