import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox

from views.overwrite_confirm import confirm_overwrite_existing


def _app() -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication([])


class OverwriteConfirmMessageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _app()

    @patch(
        "views.overwrite_confirm.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Yes,
    )
    def test_lists_each_file_with_a_bullet(self, question) -> None:
        confirm_overwrite_existing(None, ["a.bundle", "b.bundle"])

        text = question.call_args.args[2]
        self.assertIn("\u2022 a.bundle", text)
        self.assertIn("\u2022 b.bundle", text)
