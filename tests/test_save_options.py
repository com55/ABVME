import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from models.save_options import (
    CRC_LABELS,
    PACKER_LABELS,
    RESOURCE_LABELS,
    CrcMode,
    ResourcePatchMode,
    StreamCapture,
    parse_crc_mode,
    parse_packer,
    parse_resource_patch_mode,
)
from viewmodels.main_viewmodel import MainViewModel
from views.main_window import ABVMEMainWindow
from views.save_dialog import SaveDialog


def _app() -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication([])


def _plain(text: str) -> str:
    return text.replace("&", "")


def _options_menu(window: ABVMEMainWindow):
    stored = getattr(window, "_options_menu", None)
    if stored is not None:
        return stored
    for action in window.menuBar().actions():
        if _plain(action.text()) == "Options":
            menu = action.menu()
            if menu is not None:
                return menu
    raise AssertionError("Options menu missing")


def _submenu(window: ABVMEMainWindow, name: str):
    stored = {
        "Compression": getattr(window, "_compression_menu", None),
        "Resource files": getattr(window, "_resource_menu", None),
        "CRC": getattr(window, "_crc_menu", None),
    }
    menu = stored.get(name)
    if menu is not None:
        return menu
    for item in _options_menu(window).actions():
        if _plain(item.text()) == name:
            child = item.menu()
            if child is not None:
                return child
    raise AssertionError(f"submenu {name!r} missing")


def _item(menu, name: str):
    for action in menu.actions():
        if _plain(action.text()) == name:
            return action
    raise AssertionError(f"item {name!r} missing")


class SaveOptionsModelTests(unittest.TestCase):
    def test_stream_capture_fields(self) -> None:
        capture = StreamCapture(path="CAB-example.resS", offset=16, size=32)
        self.assertEqual(capture.path, "CAB-example.resS")
        self.assertEqual(capture.offset, 16)
        self.assertEqual(capture.size, 32)
        self.assertEqual(capture.image_bytes, b"")

    def test_parse_helpers_return_defaults_for_garbage(self) -> None:
        self.assertEqual(parse_packer("lz4hc"), "lz4hc")
        self.assertEqual(parse_packer("nope"), "original")
        self.assertEqual(parse_resource_patch_mode("inline"), ResourcePatchMode.INLINE)
        self.assertEqual(
            parse_resource_patch_mode("texture_patch"),
            ResourcePatchMode.RESOURCE_PATCH,
        )
        self.assertEqual(parse_crc_mode("on"), CrcMode.ON)
        self.assertEqual(parse_crc_mode("maybe"), CrcMode.AUTO)

    def test_label_maps_include_lz4hc(self) -> None:
        self.assertEqual(PACKER_LABELS["LZ4HC"], "lz4hc")
        self.assertEqual(RESOURCE_LABELS["Resource patch"], "resource_patch")
        self.assertEqual(CRC_LABELS["Auto"], "auto")


class SaveOptionsViewModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _app()

    def setUp(self) -> None:
        self.settings = QSettings("ABVMETest", "ABVME")
        self.settings.clear()
        self.vm = MainViewModel(settings=self.settings)

    def tearDown(self) -> None:
        self.settings.clear()

    def test_defaults_on_cleared_settings(self) -> None:
        self.assertEqual(self.vm.packer, "original")
        self.assertEqual(self.vm.resource_patch_mode, "resource_patch")
        self.assertEqual(self.vm.crc_mode, "auto")

    def test_setters_write_settings_keys(self) -> None:
        self.vm.set_packer("lz4hc")
        self.vm.set_resource_patch_mode("orphan_cleanup")
        self.vm.set_crc_mode("off")

        self.assertEqual(self.vm.packer, "lz4hc")
        self.assertEqual(self.vm.resource_patch_mode, "orphan_cleanup")
        self.assertEqual(self.vm.crc_mode, "off")
        self.assertEqual(self.settings.value("packer"), "lz4hc")
        self.assertEqual(self.settings.value("resource_patch_mode"), "orphan_cleanup")
        self.assertEqual(self.settings.value("crc_mode"), "off")

    def test_garbage_settings_fall_back_to_defaults(self) -> None:
        self.settings.setValue("packer", "not-a-packer")
        self.settings.setValue("resource_patch_mode", "texture_patch")
        self.settings.setValue("crc_mode", "maybe")

        vm = MainViewModel(settings=self.settings)

        self.assertEqual(vm.packer, "original")
        self.assertEqual(vm.resource_patch_mode, "resource_patch")
        self.assertEqual(vm.crc_mode, "auto")

    def test_save_all_early_return_does_not_persist(self) -> None:
        self.vm.save_all_files(
            Path("out"),
            packer="lz4",
            resource_patch_mode="inline",
            crc_mode="on",
        )

        self.assertEqual(self.settings.value("packer", "original"), "original")
        self.assertEqual(
            self.settings.value("resource_patch_mode", "resource_patch"),
            "resource_patch",
        )
        self.assertEqual(self.settings.value("crc_mode", "auto"), "auto")

    def test_save_all_unchanged_early_return_does_not_persist(self) -> None:
        unchanged = MagicMock()
        unchanged.is_changed = False
        core = MagicMock()
        core._env.files = {"bundle": unchanged}
        self.vm.core = core

        self.vm.save_all_files(
            Path("out"),
            packer="lz4",
            resource_patch_mode="inline",
            crc_mode="on",
        )

        self.assertEqual(self.settings.value("packer", "original"), "original")

    @patch("viewmodels.main_viewmodel.SaveWorker")
    def test_save_all_persists_immediately_before_worker(
        self, worker_cls: MagicMock
    ) -> None:
        worker = MagicMock()
        worker.isRunning.return_value = False
        worker_cls.return_value = worker
        changed = MagicMock()
        changed.is_changed = True
        core = MagicMock()
        core._env.files = {"bundle": changed}
        self.vm.core = core

        self.vm.save_all_files(
            Path("out"),
            packer="lz4",
            resource_patch_mode="inline",
            crc_mode="on",
        )

        self.assertEqual(self.settings.value("packer"), "lz4")
        self.assertEqual(self.settings.value("resource_patch_mode"), "inline")
        self.assertEqual(self.settings.value("crc_mode"), "on")
        worker_cls.assert_called_once()


class OptionsMenuSaveSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _app()

    def setUp(self) -> None:
        self.settings = QSettings("ABVMETest", "ABVME")
        self.settings.clear()
        self.window = ABVMEMainWindow(settings=self.settings)

    def tearDown(self) -> None:
        self.settings.clear()

    def test_options_exclusive_icon_less_groups_write_settings(self) -> None:
        expected = {
            "Compression": ["None", "LZ4", "LZ4HC", "LZMA", "Original"],
            "Resource files": ["Inline", "Orphan cleanup", "Resource patch"],
            "CRC": ["Off", "On", "Auto"],
        }
        for title, labels in expected.items():
            menu = _submenu(self.window, title)
            actions = [item for item in menu.actions() if not item.isSeparator()]
            self.assertEqual([_plain(item.text()) for item in actions], labels)
            groups = {item.actionGroup() for item in actions}
            self.assertEqual(len(groups), 1)
            group = next(iter(groups))
            self.assertIsNotNone(group)
            self.assertTrue(group.isExclusive())
            for action in actions:
                self.assertTrue(action.isCheckable())
                self.assertTrue(action.icon().isNull())

        _item(_submenu(self.window, "Compression"), "LZ4").trigger()
        self.assertEqual(self.settings.value("packer"), "lz4")
        _item(_submenu(self.window, "Compression"), "LZ4HC").trigger()
        self.assertEqual(self.settings.value("packer"), "lz4hc")
        self.assertTrue(
            _item(_submenu(self.window, "Compression"), "LZ4HC").isChecked()
        )
        self.assertFalse(_item(_submenu(self.window, "Compression"), "LZ4").isChecked())

        _item(_submenu(self.window, "Resource files"), "Inline").trigger()
        self.assertEqual(self.settings.value("resource_patch_mode"), "inline")
        _item(_submenu(self.window, "CRC"), "On").trigger()
        self.assertEqual(self.settings.value("crc_mode"), "on")

    def test_about_to_show_rebuilds_checks_from_viewmodel(self) -> None:
        self.window.viewmodel.set_packer("lzma")
        self.window.viewmodel.set_resource_patch_mode("orphan_cleanup")
        self.window.viewmodel.set_crc_mode("off")

        _options_menu(self.window).aboutToShow.emit()

        self.assertTrue(_item(_submenu(self.window, "Compression"), "LZMA").isChecked())
        self.assertTrue(
            _item(_submenu(self.window, "Resource files"), "Orphan cleanup").isChecked()
        )
        self.assertTrue(_item(_submenu(self.window, "CRC"), "Off").isChecked())

    def test_checkable_options_actions_are_icon_less(self) -> None:
        with_icon: list[str] = []
        menus = [
            _options_menu(self.window),
            _submenu(self.window, "Compression"),
            _submenu(self.window, "Resource files"),
            _submenu(self.window, "CRC"),
        ]
        for menu in menus:
            for item in menu.actions():
                if item.isSeparator() or not item.isCheckable():
                    continue
                if not item.icon().isNull():
                    with_icon.append(item.text())

        self.assertEqual(with_icon, [])


class SaveDialogScratchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _app()

    def setUp(self) -> None:
        self.settings = QSettings("ABVMETest", "ABVME")
        self.settings.clear()
        self.vm = MainViewModel(settings=self.settings)

    def tearDown(self) -> None:
        self.settings.clear()

    def test_combos_initialize_from_viewmodel(self) -> None:
        self.vm.set_packer("lz4hc")
        self.vm.set_resource_patch_mode("inline")
        self.vm.set_crc_mode("on")

        dialog = SaveDialog(self.vm)
        self.addCleanup(dialog.close)

        self.assertEqual(dialog.compression_combo.currentText(), "LZ4HC")
        self.assertEqual(dialog.resource_combo.currentText(), "Inline")
        self.assertEqual(dialog.crc_combo.currentText(), "On")

    def test_save_dialog_combo_change_does_not_persist(self) -> None:
        dialog = SaveDialog(self.vm)
        self.addCleanup(dialog.close)

        dialog.crc_combo.setCurrentText("On")
        dialog.compression_combo.setCurrentText("LZ4")
        dialog.resource_combo.setCurrentText("Inline")

        self.assertEqual(self.settings.value("crc_mode", "auto"), "auto")
        self.assertEqual(self.settings.value("packer", "original"), "original")
        self.assertEqual(
            self.settings.value("resource_patch_mode", "resource_patch"),
            "resource_patch",
        )
        self.assertEqual(self.vm.crc_mode, "auto")
        self.assertEqual(dialog._scratch_modes(), ("lz4", "inline", "on"))

    def test_save_dialog_reject_does_not_persist(self) -> None:
        dialog = SaveDialog(self.vm)
        self.addCleanup(dialog.close)
        dialog.crc_combo.setCurrentText("On")

        dialog.reject()

        self.assertEqual(self.vm.crc_mode, "auto")
        self.assertEqual(self.settings.value("crc_mode", "auto"), "auto")

    @patch("views.save_dialog.QFileDialog.getExistingDirectory", return_value="")
    def test_nested_file_dialog_cancel_does_not_accept(
        self, _get_dir: MagicMock
    ) -> None:
        dialog = SaveDialog(self.vm)
        self.addCleanup(dialog.close)
        dialog.crc_combo.setCurrentText("On")

        with patch.object(dialog, "accept") as accept:
            dialog._on_save_all_clicked()
            accept.assert_not_called()

        self.assertEqual(self.settings.value("crc_mode", "auto"), "auto")
        self.assertEqual(self.vm.crc_mode, "auto")

    @patch("views.save_dialog.QFileDialog.getExistingDirectory", return_value="out")
    def test_accept_emits_scratch_triple(self, _get_dir: MagicMock) -> None:
        dialog = SaveDialog(self.vm)
        self.addCleanup(dialog.close)
        received: list[tuple] = []
        dialog.save_all_requested.connect(lambda *args: received.append(args))
        dialog.compression_combo.setCurrentText("LZ4HC")
        dialog.resource_combo.setCurrentText("Inline")
        dialog.crc_combo.setCurrentText("On")

        dialog._on_save_all_clicked()

        self.assertEqual(received, [("out", "lz4hc", "inline", "on")])
        self.assertEqual(self.settings.value("crc_mode", "auto"), "auto")


if __name__ == "__main__":
    unittest.main()
