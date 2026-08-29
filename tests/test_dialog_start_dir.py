import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from viewmodels.main_viewmodel import MainViewModel
from views.main_window import ABVMEMainWindow


def _app() -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication([])


def _asset(source_path: str) -> SimpleNamespace:
    return SimpleNamespace(source_path=source_path)


class DialogStartDirectoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _app()

    def setUp(self) -> None:
        self.vm = MainViewModel()

    def test_no_loaded_files_uses_cwd(self) -> None:
        self.assertEqual(self.vm.get_dialog_start_directory(), str(Path.cwd()))

    def test_uses_folder_of_first_loaded_file(self) -> None:
        bundle = Path("C:/game/bundles/hero.bundle")
        self.vm.assets = [_asset(str(bundle))]

        self.assertEqual(
            Path(self.vm.get_dialog_start_directory()),
            bundle.parent,
        )

    def test_skips_empty_source_path(self) -> None:
        bundle = Path("C:/game/bundles/hero.bundle")
        self.vm.assets = [_asset(""), _asset(str(bundle))]

        self.assertEqual(
            Path(self.vm.get_dialog_start_directory()),
            bundle.parent,
        )

    def test_prefers_selected_asset_folder(self) -> None:
        first = Path("C:/game/a/one.bundle")
        second = Path("C:/game/b/two.bundle")
        self.vm.assets = [_asset(str(first)), _asset(str(second))]
        self.vm.selected_assets = [_asset(str(second))]

        self.assertEqual(
            Path(self.vm.get_dialog_start_directory()),
            second.parent,
        )


class OpenDialogUsesLoadedFolderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _app()

    def setUp(self) -> None:
        self.window = ABVMEMainWindow()
        self.bundle = Path("C:/game/bundles/hero.bundle")
        self.window.viewmodel.assets = [_asset(str(self.bundle))]

    @patch("views.main_window.QFileDialog.getOpenFileNames", return_value=([], ""))
    def test_open_files_starts_in_loaded_bundle_folder(
        self,
        get_open: MagicMock,
    ) -> None:
        self.window._on_load_button_clicked()

        self.assertEqual(Path(get_open.call_args.args[2]), self.bundle.parent)

    @patch("views.main_window.QFileDialog.getOpenFileName", return_value=("", ""))
    def test_replace_starts_in_loaded_bundle_folder(
        self,
        get_open: MagicMock,
    ) -> None:
        asset = SimpleNamespace(
            name="icon",
            container="assets/icon.png",
            obj_type=SimpleNamespace(name="Texture2D"),
            source_path=str(self.bundle),
        )
        self.window.viewmodel.get_single_selected_asset = MagicMock(return_value=asset)
        self.window.viewmodel.is_editing_supported = MagicMock(return_value=True)
        self.window.viewmodel.get_edit_file_filter = MagicMock(
            return_value="All Files (*.*)"
        )
        self.window.viewmodel.selected_assets = [asset]

        self.window._on_edit_button_clicked()

        self.assertEqual(Path(get_open.call_args.args[2]), self.bundle.parent)
