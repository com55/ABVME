"""
Application Entry Point
Main application launcher for Asset Bundles Viewer Modifier and Exporter
"""

import sys
import multiprocessing
import logging
from pathlib import Path

from PySide6.QtWidgets import QApplication

from views import ABVMEMainWindow
from utilities import LaunchCoalescer, get_resource_path


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s.%(msecs)03d] %(levelname)s (%(funcName)s): %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


def get_file_args() -> list[str]:
    """
    Extract valid file paths from command line arguments.

    Returns:
        List of valid file paths from sys.argv[1:]
    """
    file_paths = []
    for arg in sys.argv[1:]:
        path = Path(arg)
        if path.is_file():
            file_paths.append(str(path.resolve()))
    return file_paths


def load_stylesheet(app: QApplication):
    """Load QSS stylesheet"""
    try:
        stylesheet_path = get_resource_path("styles.qss")
        assets_path = get_resource_path("assets").as_posix()

        with open(stylesheet_path, "r", encoding="utf-8") as f:
            style = f.read()
            # Replace relative asset paths with absolute paths for exe compatibility
            style = style.replace("url(assets/", f"url({assets_path}/")
            app.setStyleSheet(style)
    except Exception as e:
        logging.error(f"Could not load stylesheet: {e}")


def main():
    """Main application entry point"""
    # Required for Windows multiprocessing support
    multiprocessing.freeze_support()

    file_args = get_file_args()

    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication(sys.argv)

    # Coalesce concurrent launches (e.g. multi-select Open in Explorer spawns
    # one process per file) into a single instance. Sequential launches outside
    # the collection window each spawn their own window.
    coalescer = LaunchCoalescer("ABVME_Launch")
    if not coalescer.start(file_args):
        # Files forwarded to an in-flight collector — exit silently.
        return

    app.setStyle("Fusion")
    load_stylesheet(app)

    window = ABVMEMainWindow()
    window.show()

    coalescer.pathsCollected.connect(
        lambda paths: window.viewmodel.load_files_from_paths(paths) if paths else None
    )

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
