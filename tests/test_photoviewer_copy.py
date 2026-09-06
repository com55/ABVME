import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QWidget

from views.components.photoviewer import PhotoViewer


def _app() -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication([])


class PhotoViewerCopyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _app()

    def setUp(self) -> None:
        self.parent = QWidget()
        self.viewer = PhotoViewer(self.parent)

    def test_copy_action_disabled_without_photo(self) -> None:
        menu = MagicMock()
        copy_action = MagicMock()
        menu.addAction.return_value = copy_action
        with patch("views.components.photoviewer.QtWidgets.QMenu", return_value=menu):
            self.viewer._show_context_menu(QPoint(0, 0))
        copy_action.setEnabled.assert_called_once_with(False)

    def test_copy_action_enabled_with_photo(self) -> None:
        self.viewer.setPhoto(QPixmap(16, 16))
        menu = MagicMock()
        copy_action = MagicMock()
        menu.addAction.return_value = copy_action
        menu.exec.return_value = copy_action
        with patch("views.components.photoviewer.QtWidgets.QMenu", return_value=menu):
            with patch.object(
                QApplication.clipboard(), "setPixmap"
            ) as set_pixmap:
                self.viewer._show_context_menu(QPoint(0, 0))
        copy_action.setEnabled.assert_called_once_with(True)
        set_pixmap.assert_called_once()


if __name__ == "__main__":
    unittest.main()
