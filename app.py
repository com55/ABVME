"""
Application Entry Point
Main application launcher for ModMaker Asset Viewer
"""

import sys
import multiprocessing
import logging

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication

from views import ModMakerMainWindow
from utilities import SingleInstance


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s.%(msecs)03d] %(levelname)s (%(filename)s - %(funcName)s): %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


def bring_window_to_front(window: ModMakerMainWindow):
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


def main():
    """Main application entry point"""
    # Required for Windows multiprocessing support
    multiprocessing.freeze_support()

    # Get or create QApplication instance
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
        app.setStyle("Fusion")

    # Single instance check
    single = SingleInstance("ModMakerUI_Instance")

    # If another instance is already running, don't start a new one
    if not single.start():
        print("Program already running → Showing existing window")
        return

    # Create and show main window
    window = ModMakerMainWindow()
    window.show()

    # Connect single instance signal to bring window to front
    single.messageReceived.connect(lambda: bring_window_to_front(window))

    # Start event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

