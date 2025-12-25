"""
Application Entry Point
Main application launcher for Asset Bundles Viewer Modifier and Exporter
"""

import sys
import multiprocessing
import logging
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication

from views import ABVMEMainWindow
from utilities import SingleInstance, get_resource_path


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s.%(msecs)03d] %(levelname)s (%(filename)s - %(funcName)s): %(message)s',
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


def bring_window_to_front(window: ABVMEMainWindow):
    """
    Bring existing window to front when another instance tries to start
    
    Args:
        window: Main window instance to bring to front
    """
    def do_raise():
        # Temporarily set window to stay on top
        window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        window.show()
        window.raise_()
        window.activateWindow()

        # Remove stay-on-top flag to return to normal behavior
        window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, False)
        window.show()

    QTimer.singleShot(150, do_raise)


def handle_files_received(window: ABVMEMainWindow, file_paths: list[str]):
    """
    Handle file paths received from another instance.
    
    Args:
        window: Main window instance
        file_paths: List of file paths to load
    """
    bring_window_to_front(window)
    if file_paths:
        window.viewmodel.load_files_from_paths(file_paths)

    
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

    # Get file paths from command line arguments
    file_args = get_file_args()

    # Get or create QApplication instance
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
        app.setStyle("Fusion")
        
        # Apply Stylesheet
        load_stylesheet(app)

    # Single instance check
    single = SingleInstance("ABVME_Instance")

    # If another instance is already running, send files to it and exit
    if not single.start(file_args):
        print("Program already running → Sending files to existing window")
        return

    # Create and show main window
    window = ABVMEMainWindow()
    window.show()

    # Connect single instance signal to handle files from other instances
    single.messageReceived.connect(
        lambda paths: handle_files_received(window, paths)
    )

    # Load files from command line arguments if any
    if file_args:
        QTimer.singleShot(100, lambda: window.viewmodel.load_files_from_paths(file_args))

    # Start event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
