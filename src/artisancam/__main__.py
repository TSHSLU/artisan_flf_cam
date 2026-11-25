"""Start the app: python -m artisancam [--config path/to/config.toml]"""

from __future__ import annotations

import argparse
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from .config import ConfigError, load_settings
from .ui.window import MainWindow


def main() -> int:
    parser = argparse.ArgumentParser(prog="artisancam", description="Text to G-code for the Snapmaker Artisan")
    parser.add_argument("--config", help="path to config.toml (default: the one in the project folder)")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    try:
        settings = load_settings(args.config)
    except ConfigError as exc:
        QMessageBox.critical(None, "ArtisanCAM", str(exc))
        return 1
    window = MainWindow(settings, config_path=args.config)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
