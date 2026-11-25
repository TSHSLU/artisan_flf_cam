"""The Settings dialog: edit the numbers of config.toml, save them, or restore the defaults.

The rows are generated from config.FIELDS, so every setting there appears here automatically,
on the tab its FieldSpec names. Checking and writing are done by config.save_settings, the
same rules that are applied when the file is loaded at startup. Cut-outs are not edited here;
they stay in the file.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QLocale
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..config import FIELDS, ConfigError, Settings, load_defaults, save_settings, values_of

_TABS = (
    ("layout", "Cover and text", None),
    (
        "machine",
        "Machine",
        "These values match the program that ran successfully on the machine. "
        "Change them only if you know why; “Restore defaults” brings back the known-good values.",
    ),
)


class SettingsDialog(QDialog):
    def __init__(
        self,
        settings: Settings,
        config_path: Path | str | None = None,
        defaults_path: Path | str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self._config_path = config_path
        self._defaults_path = defaults_path
        self.saved_settings: Settings | None = None  # set when Save succeeded

        self.boxes: dict[str, QDoubleSpinBox] = {}  # Settings field name -> input box
        self.tabs = QTabWidget()
        for tab_id, title, warning in _TABS:
            page = QWidget()
            page_layout = QVBoxLayout(page)
            if warning:
                note = QLabel(warning)
                note.setWordWrap(True)
                note.setStyleSheet("color: #9a3412; background: #fff7ed; padding: 6px; border-radius: 4px;")
                page_layout.addWidget(note)
            form = QFormLayout()
            for spec in FIELDS:
                if spec.tab != tab_id:
                    continue
                box = QDoubleSpinBox()
                box.setLocale(QLocale.c())  # always "0.200" like the file and the G-code, never "0,200"
                box.setDecimals(spec.decimals)
                box.setRange(0.0 if spec.may_be_zero else 10.0**-spec.decimals, spec.maximum)
                box.setSuffix(f" {spec.unit}")
                box.setToolTip(f"[{spec.section}] {spec.key} in config.toml")
                form.addRow(spec.label, box)
                self.boxes[spec.field] = box
            page_layout.addLayout(form)
            page_layout.addStretch(1)
            self.tabs.addTab(page, title)

        self.message = QLabel("")
        self.message.setWordWrap(True)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.RestoreDefaults
        )
        self.buttons.accepted.connect(self.save)
        self.buttons.rejected.connect(self.reject)
        self.buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(self.restore_defaults)

        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        layout.addWidget(self.message)
        layout.addWidget(self.buttons)
        self.set_values(values_of(settings))

    def values(self) -> dict[str, float]:
        return {field: box.value() for field, box in self.boxes.items()}

    def set_values(self, values: dict[str, float]) -> None:
        for field, value in values.items():
            self.boxes[field].setValue(value)

    def restore_defaults(self) -> None:
        """Fill in the known-good values. Nothing is written until Save is clicked."""
        try:
            defaults = load_defaults(self._defaults_path)
        except ConfigError as exc:
            self._show_error(f"Cannot read the defaults: {exc}")
            return
        self.set_values(values_of(defaults))
        self.message.setStyleSheet("color: #1d4ed8;")
        self.message.setText("Default values filled in. Click Save to keep them, or Cancel to discard.")

    def save(self) -> None:
        try:
            self.saved_settings = save_settings(self.values(), self._config_path)
        except ConfigError as exc:
            self._show_error(str(exc))
            return
        self.accept()

    def _show_error(self, text: str) -> None:
        self.message.setStyleSheet("color: #b91c1c;")
        self.message.setText(f"Not saved: {text}")
