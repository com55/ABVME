import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPlainTextEdit

from models.asset_model import PreviewResult, ResultStatus
from views.preview_panel_widget import PreviewPanelWidget


def _app() -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication([])


class PreviewDumpLazyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _app()

    def setUp(self) -> None:
        self.panel = PreviewPanelWidget()
        self.asset = SimpleNamespace(
            name="clip",
            obj_type=SimpleNamespace(name="AnimationClip"),
            get_preview=Mock(
                return_value=PreviewResult(
                    data=None,
                    asset_type="AnimationClip",
                    status=ResultStatus.UNSUPPORTED,
                    message="Preview is unavailable",
                )
            ),
            get_dump_text=Mock(return_value="dump-text"),
        )

    def test_dump_editor_does_not_wrap(self) -> None:
        self.assertEqual(
            self.panel.dump_editor.lineWrapMode(),
            QPlainTextEdit.LineWrapMode.NoWrap,
        )

    def test_selecting_asset_on_preview_tab_does_not_dump(self) -> None:
        self.panel.tab_widget.setCurrentIndex(self.panel.preview_tab_index)
        self.panel.show_asset_preview(self.asset)
        self.asset.get_preview.assert_called_once()
        self.asset.get_dump_text.assert_not_called()

    def test_opening_dump_tab_loads_once(self) -> None:
        self.panel.tab_widget.setCurrentIndex(self.panel.preview_tab_index)
        self.panel.show_asset_preview(self.asset)
        self.panel.tab_widget.setCurrentIndex(self.panel.dump_tab_index)
        self.asset.get_dump_text.assert_called_once()
        self.assertEqual(self.panel.dump_editor.toPlainText(), "dump-text")


if __name__ == "__main__":
    unittest.main()
