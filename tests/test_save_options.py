import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QStyle, QStyleOptionViewItem

from models.save_options import (
    CRC_LABELS,
    PACKER_LABELS,
    RESOURCE_LABELS,
    SAVE_OPTION_HELP,
    CrcMode,
    ResourcePatchMode,
    StreamCapture,
    parse_crc_mode,
    parse_packer,
    parse_resource_patch_mode,
    parse_show_only_changed_files,
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
        "Resource Patch Method": getattr(window, "_resource_menu", None),
        "CRC Correction": getattr(window, "_crc_menu", None),
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
        self.assertFalse(parse_show_only_changed_files(False))
        self.assertFalse(parse_show_only_changed_files(0))
        self.assertFalse(parse_show_only_changed_files("0"))
        self.assertFalse(parse_show_only_changed_files("false"))
        self.assertFalse(parse_show_only_changed_files("FALSE"))
        self.assertTrue(parse_show_only_changed_files(True))
        self.assertTrue(parse_show_only_changed_files(1))
        self.assertTrue(parse_show_only_changed_files("true"))
        self.assertTrue(parse_show_only_changed_files(None))
        self.assertTrue(parse_show_only_changed_files(""))
        self.assertTrue(parse_show_only_changed_files("maybe"))

    def test_label_maps_include_lz4hc(self) -> None:
        self.assertEqual(PACKER_LABELS["LZ4HC"], "lz4hc")
        self.assertEqual(RESOURCE_LABELS["Rebuild .resS"], "resource_patch")
        self.assertEqual(CRC_LABELS["Auto"], "auto")
        self.assertIn("compress", SAVE_OPTION_HELP["Compression Method"].lower())
        self.assertIn(".resS", SAVE_OPTION_HELP["Resource Patch Method"])
        self.assertIn("CRC32", SAVE_OPTION_HELP["CRC Correction"])
        self.assertIn("BuildTarget", SAVE_OPTION_HELP["CRC Correction"])


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
        self.assertTrue(self.vm.show_only_changed_files)

    def test_save_options_expanded_defaults_false(self) -> None:
        self.assertFalse(self.vm.save_options_expanded)

    def test_set_save_options_expanded_persists(self) -> None:
        self.vm.set_save_options_expanded(True)
        other = MainViewModel(settings=self.settings)
        self.assertTrue(other.save_options_expanded)
        self.assertTrue(self.settings.value("save_options_expanded", False, type=bool))

    def test_set_show_only_changed_files_writes_one_key(self) -> None:
        self.vm.set_show_only_changed_files(False)
        self.assertFalse(self.vm.show_only_changed_files)
        self.assertFalse(
            parse_show_only_changed_files(
                self.settings.value("show_only_changed_files")
            )
        )
        self.assertEqual(self.settings.value("packer", "original"), "original")

    def test_set_show_only_changed_files_does_not_reload_assets(self) -> None:
        received: list = []
        self.vm.assets_loaded.connect(received.append)
        self.vm.set_show_only_changed_files(False)
        self.assertEqual(received, [])

    def test_garbage_show_only_changed_files_defaults_true(self) -> None:
        self.settings.setValue("show_only_changed_files", "maybe")
        vm = MainViewModel(settings=self.settings)
        self.assertTrue(vm.show_only_changed_files)

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
            "Resource Patch Method": ["Inline", "Orphan cleanup", "Rebuild .resS"],
            "CRC Correction": ["Off", "On", "Auto"],
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

        _item(_submenu(self.window, "Resource Patch Method"), "Inline").trigger()
        self.assertEqual(self.settings.value("resource_patch_mode"), "inline")
        _item(_submenu(self.window, "CRC Correction"), "On").trigger()
        self.assertEqual(self.settings.value("crc_mode"), "on")

    def test_options_menu_nests_save_options(self) -> None:
        labels = []
        for item in _options_menu(self.window).actions():
            if item.isSeparator():
                labels.append("---")
            else:
                labels.append(_plain(item.text()))
        self.assertEqual(labels, ["Display all assets", "---", "Save Options"])
        save_options = _item(_options_menu(self.window), "Save Options")
        self.assertFalse(save_options.isCheckable())
        self.assertFalse(save_options.icon().isNull())
        nested = [
            _plain(item.text())
            for item in save_options.menu().actions()
            if not item.isSeparator()
        ]
        self.assertEqual(
            nested,
            ["Compression", "Resource Patch Method", "CRC Correction"],
        )

    def test_about_to_show_rebuilds_checks_from_viewmodel(self) -> None:
        self.window.viewmodel.set_packer("lzma")
        self.window.viewmodel.set_resource_patch_mode("orphan_cleanup")
        self.window.viewmodel.set_crc_mode("off")

        _options_menu(self.window).aboutToShow.emit()

        self.assertTrue(_item(_submenu(self.window, "Compression"), "LZMA").isChecked())
        self.assertTrue(
            _item(
                _submenu(self.window, "Resource Patch Method"), "Orphan cleanup"
            ).isChecked()
        )
        self.assertTrue(
            _item(_submenu(self.window, "CRC Correction"), "Off").isChecked()
        )

    def test_checkable_options_actions_are_icon_less(self) -> None:
        with_icon: list[str] = []
        menus = [
            _options_menu(self.window),
            _submenu(self.window, "Compression"),
            _submenu(self.window, "Resource Patch Method"),
            _submenu(self.window, "CRC Correction"),
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


def _bundle(*, changed: bool) -> MagicMock:
    obj = MagicMock()
    obj.is_changed = changed
    return obj


class SaveDialogFilterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _app()

    def setUp(self) -> None:
        self.settings = QSettings("ABVMETest", "ABVME")
        self.settings.clear()
        self.vm = MainViewModel(settings=self.settings)

    def tearDown(self) -> None:
        self.settings.clear()

    def _attach(self, files: dict[str, bool]) -> None:
        core = MagicMock()
        core._env.files = {path: _bundle(changed=flag) for path, flag in files.items()}
        self.vm.core = core

    def _assert_placeholder(self, item, text: str) -> None:
        self.assertEqual(item.text(), text)
        self.assertFalse(item.data(Qt.ItemDataRole.UserRole))
        flags = item.flags()
        self.assertFalse(bool(flags & Qt.ItemFlag.ItemIsSelectable))
        self.assertTrue(bool(flags & Qt.ItemFlag.ItemIsEnabled))

    def test_default_filter_shows_only_changed_with_leading_star(self) -> None:
        self._attach({"hero.bundle": True, "other.bundle": False})
        dialog = SaveDialog(self.vm)
        self.addCleanup(dialog.close)

        self.assertTrue(dialog.show_only_changed_checkbox.isChecked())
        self.assertEqual(dialog.file_list.count(), 1)
        item = dialog.file_list.item(0)
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item.text(), "* hero.bundle")
        self.assertEqual(item.foreground().color(), QColor("#7DCEA0"))
        self.assertEqual(item.toolTip(), "hero.bundle (modified)")
        self.assertTrue(dialog.save_all_btn.isEnabled())

    def test_option_headings_and_info_tooltips(self) -> None:
        dialog = SaveDialog(self.vm)
        self.addCleanup(dialog.close)
        self.assertEqual(dialog.compression_heading.text(), "Compression Method")
        self.assertEqual(dialog.resource_heading.text(), "Resource Patch Method")
        self.assertEqual(dialog.crc_heading.text(), "CRC Correction")
        self.assertEqual(
            dialog.compression_help.toolTip(), SAVE_OPTION_HELP["Compression Method"]
        )
        self.assertEqual(
            dialog.resource_help.toolTip(), SAVE_OPTION_HELP["Resource Patch Method"]
        )
        self.assertEqual(dialog.crc_help.toolTip(), SAVE_OPTION_HELP["CRC Correction"])
        self.assertEqual(dialog.compression_help.text(), "ⓘ")
        self.assertEqual(dialog.resource_combo.itemText(2), "Rebuild .resS")

    def test_click_uncheck_shows_unchanged_and_survives_reject(self) -> None:
        self._attach({"hero.bundle": True, "other.bundle": False})
        dialog = SaveDialog(self.vm)
        self.addCleanup(dialog.close)

        dialog.show_only_changed_checkbox.click()
        self.assertFalse(dialog.show_only_changed_checkbox.isChecked())
        texts = [
            dialog.file_list.item(i).text() for i in range(dialog.file_list.count())
        ]
        self.assertEqual(texts, ["* hero.bundle", "other.bundle"])
        unchanged = dialog.file_list.item(1)
        self.assertIsNotNone(unchanged)
        assert unchanged is not None
        self.assertIsNone(unchanged.data(Qt.ItemDataRole.ForegroundRole))
        self.assertEqual(unchanged.toolTip(), "other.bundle")
        changed = dialog.file_list.item(0)
        self.assertIsNotNone(changed)
        assert changed is not None
        self.assertEqual(changed.foreground().color(), QColor("#7DCEA0"))

        dialog.reject()
        self.assertFalse(
            parse_show_only_changed_files(
                self.settings.value("show_only_changed_files")
            )
        )

        again = SaveDialog(self.vm)
        self.addCleanup(again.close)
        self.assertFalse(again.show_only_changed_checkbox.isChecked())
        self.assertEqual(again.file_list.count(), 2)

    def test_all_unchanged_shows_no_changed_files_placeholder(self) -> None:
        self._attach({"hero.bundle": False})
        dialog = SaveDialog(self.vm)
        self.addCleanup(dialog.close)

        self.assertEqual(dialog.file_list.count(), 1)
        item = dialog.file_list.item(0)
        self.assertIsNotNone(item)
        assert item is not None
        self._assert_placeholder(item, "No changed files")
        self.assertFalse(dialog.save_selected_btn.isEnabled())
        self.assertFalse(dialog.save_all_btn.isEnabled())

    def test_no_files_loaded_even_when_filter_on(self) -> None:
        dialog = SaveDialog(self.vm)
        self.addCleanup(dialog.close)

        self.assertEqual(dialog.file_list.count(), 1)
        item = dialog.file_list.item(0)
        self.assertIsNotNone(item)
        assert item is not None
        self._assert_placeholder(item, "No files loaded")

    def test_placeholder_init_style_option_clears_mouse_over(self) -> None:
        dialog = SaveDialog(self.vm)
        self.addCleanup(dialog.close)
        index = dialog.file_list.model().index(0, 0)
        option = QStyleOptionViewItem()
        option.initFrom(dialog.file_list)
        option.state = QStyle.StateFlag.State_Enabled | QStyle.StateFlag.State_MouseOver
        delegate = dialog.file_list.itemDelegate()
        delegate.initStyleOption(option, index)
        self.assertFalse(bool(option.state & QStyle.StateFlag.State_MouseOver))

    def test_file_row_init_style_option_keeps_mouse_over(self) -> None:
        self._attach({"hero.bundle": True})
        dialog = SaveDialog(self.vm)
        self.addCleanup(dialog.close)
        index = dialog.file_list.model().index(0, 0)
        option = QStyleOptionViewItem()
        option.initFrom(dialog.file_list)
        option.state = QStyle.StateFlag.State_Enabled | QStyle.StateFlag.State_MouseOver
        delegate = dialog.file_list.itemDelegate()
        delegate.initStyleOption(option, index)
        self.assertTrue(bool(option.state & QStyle.StateFlag.State_MouseOver))

    @patch("views.save_dialog.QFileDialog.getExistingDirectory", return_value="out")
    def test_save_all_signal_stays_four_tuple_with_filter(
        self, _get_dir: MagicMock
    ) -> None:
        self._attach({"hero.bundle": True, "other.bundle": False})
        dialog = SaveDialog(self.vm)
        self.addCleanup(dialog.close)
        received: list[tuple] = []
        dialog.save_all_requested.connect(lambda *args: received.append(args))

        self.assertEqual(dialog.file_list.count(), 1)
        dialog._on_save_all_clicked()

        self.assertEqual(received, [("out", "original", "resource_patch", "auto")])
        self.assertTrue(self.vm.has_changed_files())

    def test_disclosure_is_sibling_and_starts_collapsed(self) -> None:
        dialog = SaveDialog(self.vm)
        self.addCleanup(dialog.close)
        dialog.show()
        QApplication.processEvents()

        self.assertIs(dialog.save_options_btn.parent(), dialog)
        self.assertIsNot(dialog.save_options_btn.parent(), dialog.save_options_panel)
        self.assertTrue(dialog.save_options_btn.isVisible())
        self.assertFalse(dialog.save_options_panel.isVisible())
        self.assertFalse(dialog.compression_combo.isVisible())
        self.assertEqual(dialog.save_options_btn.text(), "Save Options")
        self.assertEqual(
            dialog.save_options_btn.toolButtonStyle(),
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon,
        )
        self.assertEqual(dialog.save_options_btn.arrowType(), Qt.ArrowType.RightArrow)

        dialog.save_options_btn.click()
        QApplication.processEvents()
        self.assertTrue(dialog.save_options_panel.isVisible())
        self.assertTrue(dialog.save_options_btn.isVisible())
        self.assertEqual(dialog.save_options_btn.arrowType(), Qt.ArrowType.DownArrow)

        dialog.save_options_btn.click()
        QApplication.processEvents()
        self.assertFalse(dialog.save_options_panel.isVisible())
        self.assertEqual(dialog.save_options_btn.arrowType(), Qt.ArrowType.RightArrow)

        dialog.close()
        again = SaveDialog(self.vm)
        self.addCleanup(again.close)
        again.show()
        QApplication.processEvents()
        self.assertFalse(again.save_options_panel.isVisible())
        self.assertEqual(again.save_options_btn.arrowType(), Qt.ArrowType.RightArrow)

    def test_expanded_save_options_survives_new_dialog(self) -> None:
        dialog = SaveDialog(self.vm)
        self.addCleanup(dialog.close)
        dialog.show()
        QApplication.processEvents()
        dialog.save_options_btn.click()
        QApplication.processEvents()
        dialog.close()

        again = SaveDialog(self.vm)
        self.addCleanup(again.close)
        again.show()
        QApplication.processEvents()
        self.assertTrue(again.save_options_panel.isVisible())
        self.assertEqual(again.save_options_btn.arrowType(), Qt.ArrowType.DownArrow)
        self.assertTrue(again.save_options_btn.isChecked())


if __name__ == "__main__":
    unittest.main()
