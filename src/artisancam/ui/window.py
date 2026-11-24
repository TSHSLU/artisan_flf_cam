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
    QFormLayout,
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


class MainWindow(QWidget):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        self._program = ""
        self.setWindowTitle("ArtisanCAM")
        self.resize(1050, 720)

        self.text_input = QLineEdit()  # top line
        self.text_input.setPlaceholderText("Text near the top edge, e.g. HDMI OUT")
        self.bottom_input = QLineEdit()
        self.bottom_input.setPlaceholderText("Optional: text near the bottom edge")
        self.create_button = QPushButton("Create program")
        self.save_button = QPushButton("Save as…")
        self.save_button.setEnabled(False)
        self.status = QLabel("Enter a top and/or bottom text and click Create program.")
        self.status.setWordWrap(True)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.output.setPlaceholderText("The G-code appears here.")
        self.preview = PreviewView(settings)
        legend = QLabel("Green: engraving · dashed grey: travel · red: keep-out zones · "
                        "wheel zooms, drag pans, double-click fits")
        legend.setWordWrap(True)
        legend.setStyleSheet("color: #5b6670; font-size: 11px;")

        form = QFormLayout()
        form.addRow("Top text", self.text_input)
        form.addRow("Bottom text", self.bottom_input)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.create_button)
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

        self.create_button.clicked.connect(self.create)
        for field in (self.text_input, self.bottom_input):
            field.returnPressed.connect(self.create)
            field.textChanged.connect(self._text_changed)
        self.save_button.clicked.connect(self.save)

    def create(self) -> None:
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
