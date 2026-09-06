import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox

from viewmodels.main_viewmodel import MainViewModel
from views.main_window import ABVMEMainWindow


def _app() -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication([])


class BundleFilesInDirectoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.settings = QSettings(
            str(self.tmp / "abvme.ini"), QSettings.Format.IniFormat
        )
        self.vm = MainViewModel(settings=self.settings)

    def tearDown(self) -> None:
        self.settings.clear()
        self._tmp.cleanup()

    def test_lists_only_top_level_bundle_and_unity3d(self) -> None:
        (self.tmp / "a.bundle").write_bytes(b"x")
        (self.tmp / "b.unity3d").write_bytes(b"x")
        (self.tmp / "notes.txt").write_bytes(b"x")
        nested = self.tmp / "sub"
        nested.mkdir()
        (nested / "hidden.bundle").write_bytes(b"x")

        names = [Path(p).name for p in self.vm.bundle_files_in_directory(str(self.tmp))]

        self.assertEqual(names, ["a.bundle", "b.unity3d"])

    def test_empty_or_missing_directory_returns_empty(self) -> None:
        empty = self.tmp / "empty"
        empty.mkdir()
        self.assertEqual(self.vm.bundle_files_in_directory(str(empty)), [])
        self.assertEqual(
            self.vm.bundle_files_in_directory(str(self.tmp / "missing")),
            [],
        )


class RememberOpenDirectoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.desktop = self.tmp / "Desktop"
        self.desktop.mkdir()
        self.settings = QSettings(
            str(self.tmp / "abvme.ini"), QSettings.Format.IniFormat
        )
        self.desktop_patch = patch(
            "viewmodels.main_viewmodel.desktop_directory",
            return_value=str(self.desktop),
            create=True,
        )
        self.desktop_patch.start()
        self.vm = MainViewModel(settings=self.settings)

    def tearDown(self) -> None:
        self.desktop_patch.stop()
        self.settings.clear()
        self._tmp.cleanup()

    def test_remembers_chosen_folder_without_files(self) -> None:
        folder = self.tmp / "bundles"
        folder.mkdir()
        self.vm.remember_open_directory(str(folder))

        self.assertEqual(
            Path(self.vm.get_open_dialog_start_directory()),
            folder,
        )


class OpenFolderMenuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _app()

    def test_file_menu_order_without_close(self) -> None:
        self.window = ABVMEMainWindow()
        labels = []
        for item in self.window._file_menu.actions():
            if item.isSeparator():
                labels.append("---")
            else:
                labels.append(item.text().replace("&", ""))

        self.assertEqual(
            labels,
            ["Open Files...", "Open Folder...", "Save as...", "---", "Exit"],
        )

    def test_open_folder_shortcut_is_ctrl_shift_o(self) -> None:
        self.window = ABVMEMainWindow()
        self.assertEqual(
            self.window.open_folder_action.shortcut().toString(),
            "Ctrl+Shift+O",
        )


class OpenFolderDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _app()

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.desktop = self.tmp / "Desktop"
        self.desktop.mkdir()
        self.settings = QSettings(
            str(self.tmp / "abvme.ini"), QSettings.Format.IniFormat
        )
        self.desktop_patch = patch(
            "viewmodels.main_viewmodel.desktop_directory",
            return_value=str(self.desktop),
            create=True,
        )
        self.desktop_patch.start()
        self.window = ABVMEMainWindow(settings=self.settings)

    def tearDown(self) -> None:
        self.desktop_patch.stop()
        self.settings.clear()
        self._tmp.cleanup()

    @patch("views.main_window.QFileDialog.getExistingDirectory", return_value="")
    def test_cancel_does_not_load(self, get_dir: MagicMock) -> None:
        self.window.viewmodel.load_files_from_paths = MagicMock()

        self.window._on_open_folder_clicked()

        self.window.viewmodel.load_files_from_paths.assert_not_called()
        self.assertEqual(Path(get_dir.call_args.args[2]), self.desktop)

    @patch("views.main_window.QFileDialog.getExistingDirectory")
    def test_empty_folder_remembers_and_does_not_load(self, get_dir: MagicMock) -> None:
        folder = self.tmp / "empty"
        folder.mkdir()
        get_dir.return_value = str(folder)
        self.window.viewmodel.load_files_from_paths = MagicMock()

        self.window._on_open_folder_clicked()

        self.window.viewmodel.load_files_from_paths.assert_not_called()
        self.assertEqual(
            Path(self.window.viewmodel.get_open_dialog_start_directory()),
            folder,
        )

    @patch("views.main_window.QFileDialog.getExistingDirectory")
    def test_loads_bundle_files_from_folder(self, get_dir: MagicMock) -> None:
        folder = self.tmp / "game"
        folder.mkdir()
        bundle = folder / "hero.bundle"
        bundle.write_bytes(b"x")
        (folder / "readme.txt").write_bytes(b"x")
        get_dir.return_value = str(folder)
        self.window.viewmodel.load_files_from_paths = MagicMock()

        self.window._on_open_folder_clicked()

        loaded = self.window.viewmodel.load_files_from_paths.call_args.args[0]
        self.assertEqual([Path(p).name for p in loaded], ["hero.bundle"])

    @patch("views.main_window.QMessageBox.question")
    @patch("views.main_window.QFileDialog.getExistingDirectory")
    def test_one_hundred_files_loads_without_confirm(
        self, get_dir: MagicMock, question: MagicMock
    ) -> None:
        folder = self.tmp / "many"
        folder.mkdir()
        get_dir.return_value = str(folder)
        files = [str(folder / f"{i}.bundle") for i in range(100)]
        self.window.viewmodel.bundle_files_in_directory = MagicMock(return_value=files)
        self.window.viewmodel.load_files_from_paths = MagicMock()

        self.window._on_open_folder_clicked()

        question.assert_not_called()
        self.window.viewmodel.load_files_from_paths.assert_called_once_with(files)

    @patch(
        "views.main_window.QMessageBox.question",
        return_value=QMessageBox.StandardButton.No,
    )
    @patch("views.main_window.QFileDialog.getExistingDirectory")
    def test_over_one_hundred_files_no_does_not_load(
        self, get_dir: MagicMock, question: MagicMock
    ) -> None:
        folder = self.tmp / "many"
        folder.mkdir()
        get_dir.return_value = str(folder)
        files = [str(folder / f"{i}.bundle") for i in range(101)]
        self.window.viewmodel.bundle_files_in_directory = MagicMock(return_value=files)
        self.window.viewmodel.load_files_from_paths = MagicMock()

        self.window._on_open_folder_clicked()

        question.assert_called_once()
        self.window.viewmodel.load_files_from_paths.assert_not_called()

    @patch(
        "views.main_window.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Yes,
    )
    @patch("views.main_window.QFileDialog.getExistingDirectory")
    def test_over_one_hundred_files_yes_loads(
        self, get_dir: MagicMock, question: MagicMock
    ) -> None:
        folder = self.tmp / "many"
        folder.mkdir()
        get_dir.return_value = str(folder)
        files = [str(folder / f"{i}.bundle") for i in range(101)]
        self.window.viewmodel.bundle_files_in_directory = MagicMock(return_value=files)
        self.window.viewmodel.load_files_from_paths = MagicMock()

        self.window._on_open_folder_clicked()

        self.window.viewmodel.load_files_from_paths.assert_called_once_with(files)
