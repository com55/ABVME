import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QSizePolicy

from utilities.updater import ReleaseAsset, UpdateInfo
from views.update_dialog import UpdateDialog


def _app() -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication([])


class UpdateDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _app()

    def test_shows_versions_and_buttons(self) -> None:
        update = UpdateInfo(
            current_version="0.1.9",
            latest_version="0.2.0",
            release_name="ABVME v0.2.0",
            release_url="https://github.com/com55/ABVME/releases/tag/v0.2.0",
            tag_name="v0.2.0",
            body="## Notes\n- fix",
            assets=[
                ReleaseAsset(
                    "ABVME-Windows-x64-Setup.exe", "https://example.invalid/s", 1
                )
            ],
        )
        dialog = UpdateDialog(None, update=update)
        self.addCleanup(dialog.close)
        self.assertIn("0.1.9", dialog.summary_label.text())
        self.assertIn("0.2.0", dialog.summary_label.text())
        self.assertEqual(dialog.release_name_label.text(), "ABVME v0.2.0")
        self.assertIn("font-weight: bold", dialog.release_name_label.styleSheet())
        self.assertIn("14pt", dialog.release_name_label.styleSheet())
        self.assertIn("fix", dialog.body_view.toPlainText())
        # GitHub-flavored markdown: heading should render, not stay as "## Notes"
        self.assertNotIn("## Notes", dialog.body_view.toPlainText())
        self.assertEqual(dialog.update_now_button.text(), "Update Now")
        self.assertEqual(dialog.view_github_button.text(), "View on GitHub")
        self.assertFalse(dialog.progress_bar.isVisible())
        self.assertTrue(dialog._buttons_spacer.isVisibleTo(dialog))
        self.assertTrue(dialog.progress_bar.isTextVisible())
        self.assertEqual(
            dialog.progress_bar.sizePolicy().horizontalPolicy(),
            QSizePolicy.Policy.Expanding,
        )
        self.assertIn("QProgressBar::chunk", dialog.progress_bar.styleSheet())
        self.assertTrue(dialog.body_view.openExternalLinks())

        dialog._set_progress_visible(True)
        self.assertTrue(dialog.progress_bar.isVisibleTo(dialog))
        self.assertFalse(dialog._buttons_spacer.isVisibleTo(dialog))
        dialog._set_progress_visible(False)
        self.assertFalse(dialog.progress_bar.isVisibleTo(dialog))
        self.assertTrue(dialog._buttons_spacer.isVisibleTo(dialog))


if __name__ == "__main__":
    unittest.main()
