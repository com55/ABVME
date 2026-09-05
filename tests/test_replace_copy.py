import inspect
import logging
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QMimeData, QPointF, QUrl, Qt
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QApplication, QMessageBox

from models.asset_model import AssetInfo, EditResult, ResultStatus
from viewmodels.main_viewmodel import MainViewModel
from views.main_window import ABVMEMainWindow


def _app() -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication([])


class FakeAsset(AssetInfo):
    def __init__(
        self,
        name: str = "hero",
        type_name: str = "TextAsset",
        container: str = "assets/hero.skel.bytes",
    ) -> None:
        self.name = name
        self.container = container
        self.obj_type = SimpleNamespace(name=type_name)


class ReplaceCopyViewModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _app()

    def setUp(self) -> None:
        self.log_patcher = patch("viewmodels.main_viewmodel.log")
        self.log_patcher.start()
        self.addCleanup(self.log_patcher.stop)
        self.vm = MainViewModel()
        self.started: list[str] = []
        self.status: list[tuple[str, int]] = []
        self.vm.edit_started.connect(self.started.append)
        self.vm.status_message.connect(
            lambda msg, level: self.status.append((msg, level))
        )

    @patch("viewmodels.main_viewmodel.EditWorker")
    def test_edit_asset_emits_replacing_status(self, worker_cls: MagicMock) -> None:
        worker = MagicMock()
        worker.isRunning.return_value = False
        worker_cls.return_value = worker
        asset = FakeAsset(name="icon")

        started = self.vm.edit_asset(asset, "icon.png")

        self.assertTrue(started)
        self.assertEqual(self.started, ["Replacing icon..."])
        worker.start.assert_called_once()

    def test_busy_worker_emits_another_replace_running(self) -> None:
        busy = MagicMock()
        busy.isRunning.return_value = True
        self.vm.edit_worker = busy

        started = self.vm.edit_asset(FakeAsset(name="icon"), "icon.png")

        self.assertFalse(started)
        self.assertEqual(
            self.status,
            [("Another replace is currently running.", logging.WARNING)],
        )

    def test_finished_fallback_uses_replaced_copy(self) -> None:
        asset = FakeAsset(name="icon")
        result = EditResult(status=ResultStatus.COMPLETE, message="")
        self.vm._on_edit_finished(asset, result)
        self.assertEqual(self.status[0][0], "Replaced icon")

    def test_finished_fallback_uses_failed_to_replace_copy(self) -> None:
        asset = FakeAsset(name="icon")
        result = EditResult(status=ResultStatus.ERROR, message="")
        self.vm._on_edit_finished(asset, result)
        self.assertEqual(self.status[0][0], "Failed to replace icon")


class ReplaceCopyWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _app()

    def setUp(self) -> None:
        self.window = ABVMEMainWindow()

    def test_edit_button_label_is_replace(self) -> None:
        self.assertEqual(self.window.edit_button.text(), "  Replace")

    def test_unsupported_type_uses_replace_copy(self) -> None:
        asset = FakeAsset(name="mesh", type_name="Mesh")
        messages: list[tuple[str, int]] = []
        self.window.viewmodel.get_single_selected_asset = MagicMock(return_value=asset)
        self.window.viewmodel.is_editing_supported = MagicMock(return_value=False)
        self.window._on_status_message = lambda msg, level: messages.append(
            (msg, level)
        )

        self.window._on_edit_button_clicked()

        self.assertEqual(
            messages,
            [("Replace is not supported for Mesh.", logging.WARNING)],
        )

    @patch.object(ABVMEMainWindow, "_ask_yes_no")
    @patch("views.main_window.QFileDialog.getOpenFileName")
    def test_file_dialog_caption_is_select_replacement_file(
        self,
        get_open: MagicMock,
        ask: MagicMock,
    ) -> None:
        get_open.return_value = ("", "")
        asset = FakeAsset(type_name="Texture2D", container="assets/icon.png")
        self.window.viewmodel.get_single_selected_asset = MagicMock(return_value=asset)
        self.window.viewmodel.is_editing_supported = MagicMock(return_value=True)
        self.window.viewmodel.get_edit_file_filter = MagicMock(
            return_value="All Files (*.*)"
        )

        self.window._on_edit_button_clicked()

        self.assertEqual(get_open.call_args.args[1], "Select replacement file")
        ask.assert_not_called()

    @patch.object(ABVMEMainWindow, "_ask_yes_no", return_value=True)
    @patch(
        "views.main_window.QFileDialog.getOpenFileName",
        return_value=("icon.png", ""),
    )
    def test_file_dialog_texture_confirms_replace(
        self,
        _get_open: MagicMock,
        ask: MagicMock,
    ) -> None:
        asset = FakeAsset(
            name="Icon", type_name="Texture2D", container="assets/icon.png"
        )
        self.window.viewmodel.get_single_selected_asset = MagicMock(return_value=asset)
        self.window.viewmodel.is_editing_supported = MagicMock(return_value=True)
        self.window.viewmodel.get_edit_file_filter = MagicMock(
            return_value="All Files (*.*)"
        )
        self.window.viewmodel.edit_asset = MagicMock(return_value=True)

        self.window._on_edit_button_clicked()

        self.assertTrue(ask.called)
        self.assertEqual(ask.call_args.args[0], "Confirm Replace")
        self.assertEqual(ask.call_args.args[1], "Replace 'Icon' with 'icon.png'?")
        self.window.viewmodel.edit_asset.assert_called_once_with(asset, "icon.png")

    @patch.object(ABVMEMainWindow, "_ask_yes_no", return_value=False)
    @patch(
        "views.main_window.QFileDialog.getOpenFileName",
        return_value=("icon.png", ""),
    )
    def test_file_dialog_texture_confirm_no_skips_edit(
        self,
        _get_open: MagicMock,
        _ask: MagicMock,
    ) -> None:
        asset = FakeAsset(
            name="Icon", type_name="Texture2D", container="assets/icon.png"
        )
        self.window.viewmodel.get_single_selected_asset = MagicMock(return_value=asset)
        self.window.viewmodel.is_editing_supported = MagicMock(return_value=True)
        self.window.viewmodel.get_edit_file_filter = MagicMock(
            return_value="All Files (*.*)"
        )
        self.window.viewmodel.edit_asset = MagicMock(return_value=True)

        self.window._on_edit_button_clicked()

        self.window.viewmodel.edit_asset.assert_not_called()

    @patch.object(ABVMEMainWindow, "_ask_yes_no", return_value=True)
    @patch(
        "views.main_window.QFileDialog.getOpenFileName",
        return_value=("hero.json", ""),
    )
    def test_file_dialog_textasset_unmatched_suffix_confirms(
        self,
        _get_open: MagicMock,
        ask: MagicMock,
    ) -> None:
        asset = FakeAsset(
            name="hero",
            type_name="TextAsset",
            container="assets/hero.skel.bytes",
        )
        self.window.viewmodel.get_single_selected_asset = MagicMock(return_value=asset)
        self.window.viewmodel.is_editing_supported = MagicMock(return_value=True)
        self.window.viewmodel.get_edit_file_filter = MagicMock(
            return_value="All Files (*.*)"
        )
        self.window.viewmodel.edit_asset = MagicMock(return_value=True)

        self.window._on_edit_button_clicked()

        self.assertEqual(ask.call_args.args[0], "Confirm Replace")
        self.assertEqual(
            ask.call_args.args[1],
            "The suffix of 'hero.json' is not in the container of 'hero'. Replace anyway?",
        )
        self.window.viewmodel.edit_asset.assert_called_once_with(asset, "hero.json")

    @patch.object(ABVMEMainWindow, "_ask_yes_no", return_value=True)
    @patch(
        "views.main_window.QFileDialog.getOpenFileName",
        return_value=("hero.skel", ""),
    )
    def test_file_dialog_textasset_matched_suffix_confirms(
        self,
        _get_open: MagicMock,
        ask: MagicMock,
    ) -> None:
        asset = FakeAsset(
            name="hero",
            type_name="TextAsset",
            container="assets/hero.skel.bytes",
        )
        self.window.viewmodel.get_single_selected_asset = MagicMock(return_value=asset)
        self.window.viewmodel.is_editing_supported = MagicMock(return_value=True)
        self.window.viewmodel.get_edit_file_filter = MagicMock(
            return_value="All Files (*.*)"
        )
        self.window.viewmodel.edit_asset = MagicMock(return_value=True)

        self.window._on_edit_button_clicked()

        self.assertTrue(ask.called)
        self.assertEqual(ask.call_args.args[0], "Confirm Replace")
        self.assertEqual(ask.call_args.args[1], "Replace 'hero' with 'hero.skel'?")
        self.window.viewmodel.edit_asset.assert_called_once_with(asset, "hero.skel")

    @patch.object(ABVMEMainWindow, "_ask_yes_no", return_value=False)
    @patch(
        "views.main_window.QFileDialog.getOpenFileName",
        return_value=("hero.json", ""),
    )
    def test_file_dialog_textasset_confirm_no_skips_edit(
        self,
        _get_open: MagicMock,
        _ask: MagicMock,
    ) -> None:
        asset = FakeAsset(
            name="hero",
            type_name="TextAsset",
            container="assets/hero.skel.bytes",
        )
        self.window.viewmodel.get_single_selected_asset = MagicMock(return_value=asset)
        self.window.viewmodel.is_editing_supported = MagicMock(return_value=True)
        self.window.viewmodel.get_edit_file_filter = MagicMock(
            return_value="All Files (*.*)"
        )
        self.window.viewmodel.edit_asset = MagicMock(return_value=True)

        self.window._on_edit_button_clicked()

        self.window.viewmodel.edit_asset.assert_not_called()


class AskYesNoDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _app()

    def setUp(self) -> None:
        self.window = ABVMEMainWindow()

    def test_ask_yes_no_keeps_dialog_in_front(self) -> None:
        boxes: list[QMessageBox] = []

        def fake_exec(box: QMessageBox) -> QMessageBox.StandardButton:
            boxes.append(box)
            return QMessageBox.StandardButton.Yes

        with patch.object(QMessageBox, "exec", fake_exec):
            result = self.window._ask_yes_no("Confirm Replace", "body")

        self.assertTrue(result)
        self.assertEqual(len(boxes), 1)
        box = boxes[0]
        flags = box.windowFlags()
        self.assertTrue(flags & Qt.WindowType.WindowStaysOnTopHint)
        self.assertEqual(box.windowModality(), Qt.WindowModality.ApplicationModal)
        self.assertTrue(box.isVisible())
        self.assertEqual(box.windowTitle(), "Confirm Replace")
        self.assertEqual(box.text(), "body")
        box.hide()


class ReplaceCopyDropTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _app()

    def setUp(self) -> None:
        self.window = ABVMEMainWindow()
        self._tmp = tempfile.TemporaryDirectory()
        self.png_path = str(Path(self._tmp.name) / "icon.png")
        self.json_path = str(Path(self._tmp.name) / "hero.json")
        Path(self.png_path).write_bytes(b"png")
        Path(self.json_path).write_text("{}", encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _drop(self, file_path: str) -> QDropEvent:
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(file_path)])
        event = QDropEvent(
            QPointF(10, 10),
            Qt.DropAction.CopyAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        self._mime = mime
        return event

    @patch.object(ABVMEMainWindow, "_ask_yes_no", return_value=True)
    def test_texture_drop_confirm_copy(self, ask: MagicMock) -> None:
        asset = FakeAsset(
            name="Icon", type_name="Texture2D", container="assets/icon.png"
        )
        self.window.viewmodel.get_single_selected_asset = MagicMock(return_value=asset)
        self.window.viewmodel.is_editing_supported = MagicMock(return_value=True)
        self.window.viewmodel.edit_asset = MagicMock(return_value=True)

        self.window.dropEvent(self._drop(self.png_path))

        self.assertEqual(ask.call_args.args[0], "Confirm Replace")
        self.assertEqual(
            ask.call_args.args[1],
            f"Replace 'Icon' with '{Path(self.png_path).name}'?",
        )
        self.window.viewmodel.edit_asset.assert_called_once()
        called_asset, called_path = self.window.viewmodel.edit_asset.call_args.args
        self.assertIs(called_asset, asset)
        self.assertEqual(Path(called_path), Path(self.png_path))

    @patch.object(ABVMEMainWindow, "_ask_yes_no", return_value=True)
    def test_textasset_drop_unmatched_suffix_confirm_copy(self, ask: MagicMock) -> None:
        asset = FakeAsset(
            name="hero",
            type_name="TextAsset",
            container="assets/hero.skel.bytes",
        )
        self.window.viewmodel.get_single_selected_asset = MagicMock(return_value=asset)
        self.window.viewmodel.is_editing_supported = MagicMock(return_value=True)
        self.window.viewmodel.edit_asset = MagicMock(return_value=True)

        self.window.dropEvent(self._drop(self.json_path))

        self.assertEqual(ask.call_args.args[0], "Confirm Replace")
        self.assertEqual(
            ask.call_args.args[1],
            "The suffix of 'hero.json' is not in the container of 'hero'. Replace anyway?",
        )
        self.window.viewmodel.edit_asset.assert_called_once()
        called_asset, called_path = self.window.viewmodel.edit_asset.call_args.args
        self.assertIs(called_asset, asset)
        self.assertEqual(Path(called_path), Path(self.json_path))

    @patch.object(ABVMEMainWindow, "_ask_yes_no", return_value=True)
    def test_textasset_drop_matched_suffix_confirms(self, ask: MagicMock) -> None:
        asset = FakeAsset(
            name="hero",
            type_name="TextAsset",
            container="assets/hero.skel.bytes",
        )
        skel_path = str(Path(self._tmp.name) / "hero.skel")
        Path(skel_path).write_bytes(b"skel")
        self.window.viewmodel.get_single_selected_asset = MagicMock(return_value=asset)
        self.window.viewmodel.is_editing_supported = MagicMock(return_value=True)
        self.window.viewmodel.edit_asset = MagicMock(return_value=True)

        self.window.dropEvent(self._drop(skel_path))

        self.assertTrue(ask.called)
        self.assertEqual(ask.call_args.args[0], "Confirm Replace")
        self.assertEqual(ask.call_args.args[1], "Replace 'hero' with 'hero.skel'?")
        self.window.viewmodel.edit_asset.assert_called_once()
        called_asset, called_path = self.window.viewmodel.edit_asset.call_args.args
        self.assertIs(called_asset, asset)
        self.assertEqual(Path(called_path), Path(skel_path))


class ReplaceCopyModelTests(unittest.TestCase):
    def test_edit_data_success_messages_use_replaced(self) -> None:
        source = inspect.getsource(AssetInfo.edit_data)
        self.assertIn('message="Texture2D replaced successfully."', source)
        self.assertIn('message="TextAsset replaced successfully."', source)
        self.assertIn("Replace is not supported for", source)
        self.assertNotIn("updated successfully", source)
        self.assertNotIn("Editing not supported", source)


if __name__ == "__main__":
    unittest.main()
