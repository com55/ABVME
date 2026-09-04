import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from viewmodels.main_viewmodel import MainViewModel
from views.main_window import ABVMEMainWindow
from views.save_dialog import SaveDialog


def _app() -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication([])


def _asset(source_path: str, **kwargs: object) -> SimpleNamespace:
    data = {
        "source_path": source_path,
        "name": "icon",
        "container": "assets/icon.png",
        "path_id": "1",
        "obj_type": SimpleNamespace(name="Texture2D"),
    }
    data.update(kwargs)
    return SimpleNamespace(**data)


class _DialogDirTests(unittest.TestCase):
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
        self.settings.clear()
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

    def _bundle(self, folder: str, name: str = "hero.bundle") -> Path:
        path = self.tmp / folder
        path.mkdir(parents=True, exist_ok=True)
        bundle = path / name
        bundle.write_bytes(b"bundle")
        return bundle


class OpenDialogDirectoryTests(_DialogDirTests):
    def test_no_setting_uses_desktop(self) -> None:
        self.assertEqual(
            Path(self.vm.get_open_dialog_start_directory()),
            self.desktop,
        )

    def test_remembers_folder_of_opened_file(self) -> None:
        bundle = self._bundle("game")
        self.vm.remember_open_directory_from_paths([str(bundle)])

        self.assertEqual(
            Path(self.vm.get_open_dialog_start_directory()),
            bundle.parent,
        )

    def test_open_folder_persists_in_settings(self) -> None:
        bundle = self._bundle("game")
        self.vm.remember_open_directory_from_paths([str(bundle)])

        other = MainViewModel(settings=self.settings)
        self.assertEqual(
            Path(other.get_open_dialog_start_directory()),
            bundle.parent,
        )

    def test_missing_remembered_folder_uses_desktop(self) -> None:
        gone = self.tmp / "deleted"
        gone.mkdir()
        bundle = gone / "a.bundle"
        bundle.write_bytes(b"x")
        self.vm.remember_open_directory_from_paths([str(bundle)])
        bundle.unlink()
        gone.rmdir()

        self.assertEqual(
            Path(self.vm.get_open_dialog_start_directory()),
            self.desktop,
        )

    @patch("viewmodels.main_viewmodel.LoaderWorker")
    def test_load_files_remembers_open_folder(self, worker_cls: MagicMock) -> None:
        worker_cls.return_value = MagicMock()
        bundle = self._bundle("from_load")
        self.vm.load_files_from_paths([str(bundle)])

        self.assertEqual(
            Path(self.vm.get_open_dialog_start_directory()),
            bundle.parent,
        )


class OutputDialogDirectoryTests(_DialogDirTests):
    def test_first_use_is_loaded_bundle_folder(self) -> None:
        bundle = self._bundle("game")
        self.vm.assets = [_asset(str(bundle))]

        self.assertEqual(
            Path(self.vm.get_output_dialog_start_directory()),
            bundle.parent,
        )

    def test_prefers_selected_asset_folder(self) -> None:
        first = self._bundle("a", "one.bundle")
        second = self._bundle("b", "two.bundle")
        self.vm.assets = [_asset(str(first)), _asset(str(second))]
        self.vm.selected_assets = [_asset(str(second))]

        self.assertEqual(
            Path(self.vm.get_output_dialog_start_directory()),
            second.parent,
        )

    def test_remembers_session_folder_not_settings(self) -> None:
        bundle = self._bundle("game")
        out = self.tmp / "export"
        out.mkdir()
        self.vm.assets = [_asset(str(bundle))]
        self.vm.remember_output_directory(str(out))

        self.assertEqual(Path(self.vm.get_output_dialog_start_directory()), out)
        self.assertIsNone(self.settings.value("last_open_directory"))
        other = MainViewModel(settings=self.settings)
        other.assets = [_asset(str(bundle))]
        self.assertEqual(
            Path(other.get_output_dialog_start_directory()),
            bundle.parent,
        )

    def test_missing_session_folder_uses_loaded_bundle(self) -> None:
        bundle = self._bundle("game")
        out = self.tmp / "gone_out"
        out.mkdir()
        self.vm.assets = [_asset(str(bundle))]
        self.vm.remember_output_directory(str(out))
        out.rmdir()

        self.assertEqual(
            Path(self.vm.get_output_dialog_start_directory()),
            bundle.parent,
        )

    @patch("viewmodels.main_viewmodel.SaveWorker")
    def test_save_all_remembers_output_folder(self, worker_cls: MagicMock) -> None:
        worker_cls.return_value = MagicMock()
        bundle = self._bundle("game")
        out = self.tmp / "saved"
        out.mkdir()
        self.vm.assets = [_asset(str(bundle))]
        self.vm.core = SimpleNamespace(_env=SimpleNamespace(files={}))
        self.vm.has_changed_files = MagicMock(return_value=True)
        self.vm._start_save_worker = MagicMock()

        self.vm.save_all_files(out)

        self.assertEqual(Path(self.vm.get_output_dialog_start_directory()), out)

    def test_export_single_remembers_output_folder(self) -> None:
        bundle = self._bundle("game")
        out = self.tmp / "shot.png"
        self.vm.assets = [_asset(str(bundle))]
        asset = MagicMock()
        asset.name = "icon"
        asset.export.return_value = SimpleNamespace(is_success=True, message="ok")

        self.vm.export_single_asset(asset, out)

        self.assertEqual(
            Path(self.vm.get_output_dialog_start_directory()),
            out.parent,
        )


class ReplaceDialogDirectoryTests(_DialogDirTests):
    def test_first_use_is_loaded_bundle_folder(self) -> None:
        bundle = self._bundle("game")
        self.vm.assets = [_asset(str(bundle))]

        self.assertEqual(
            Path(self.vm.get_replace_dialog_start_directory()),
            bundle.parent,
        )

    def test_remembers_session_folder_not_settings(self) -> None:
        bundle = self._bundle("game")
        repl = self.tmp / "tex"
        repl.mkdir()
        png = repl / "a.png"
        png.write_bytes(b"x")
        self.vm.assets = [_asset(str(bundle))]
        self.vm.remember_replace_directory_from_path(str(png))

        self.assertEqual(Path(self.vm.get_replace_dialog_start_directory()), repl)
        other = MainViewModel(settings=self.settings)
        other.assets = [_asset(str(bundle))]
        self.assertEqual(
            Path(other.get_replace_dialog_start_directory()),
            bundle.parent,
        )

    def test_missing_session_folder_uses_loaded_bundle(self) -> None:
        bundle = self._bundle("game")
        repl = self.tmp / "tex"
        repl.mkdir()
        png = repl / "a.png"
        png.write_bytes(b"x")
        self.vm.assets = [_asset(str(bundle))]
        self.vm.remember_replace_directory_from_path(str(png))
        png.unlink()
        repl.rmdir()

        self.assertEqual(
            Path(self.vm.get_replace_dialog_start_directory()),
            bundle.parent,
        )

    @patch("viewmodels.main_viewmodel.EditWorker")
    def test_edit_asset_remembers_replace_folder(self, worker_cls: MagicMock) -> None:
        worker = MagicMock()
        worker.isRunning.return_value = False
        worker_cls.return_value = worker
        bundle = self._bundle("game")
        repl = self.tmp / "tex"
        repl.mkdir()
        png = repl / "a.png"
        png.write_bytes(b"x")
        self.vm.assets = [_asset(str(bundle))]

        self.vm.edit_asset(_asset(str(bundle)), str(png))

        self.assertEqual(Path(self.vm.get_replace_dialog_start_directory()), repl)


class DialogWiringTests(_DialogDirTests):
    def setUp(self) -> None:
        super().setUp()
        self.window = ABVMEMainWindow(settings=self.settings)
        self.bundle = self._bundle("game")
        self.window.viewmodel.assets = [_asset(str(self.bundle))]

    @patch("views.main_window.QFileDialog.getOpenFileNames", return_value=([], ""))
    def test_open_files_uses_open_start_directory(self, get_open: MagicMock) -> None:
        remembered = self._bundle("last_open")
        self.window.viewmodel.remember_open_directory_from_paths([str(remembered)])
        self.assertEqual(
            Path(self.window.viewmodel.get_open_dialog_start_directory()),
            remembered.parent,
            msg=repr(self.settings.value("last_open_directory")),
        )

        self.window._on_load_button_clicked()

        self.assertEqual(Path(get_open.call_args.args[2]), remembered.parent)

    @patch("views.main_window.QFileDialog.getOpenFileName", return_value=("", ""))
    def test_replace_uses_replace_start_directory(self, get_open: MagicMock) -> None:
        asset = _asset(str(self.bundle))
        self.window.viewmodel.get_single_selected_asset = MagicMock(return_value=asset)
        self.window.viewmodel.is_editing_supported = MagicMock(return_value=True)
        self.window.viewmodel.get_edit_file_filter = MagicMock(
            return_value="All Files (*.*)"
        )
        self.window.viewmodel.selected_assets = [asset]

        self.window._on_edit_button_clicked()

        self.assertEqual(Path(get_open.call_args.args[2]), self.bundle.parent)

    @patch("views.main_window.QFileDialog.getSaveFileName", return_value=("", ""))
    def test_export_single_uses_output_start_directory(
        self, get_save: MagicMock
    ) -> None:
        out = self.tmp / "exports"
        out.mkdir()
        self.window.viewmodel.remember_output_directory(str(out))
        asset = _asset(str(self.bundle))
        self.window.viewmodel.selected_assets = [asset]
        self.window.viewmodel.get_suggested_export_filename = MagicMock(
            return_value="icon.png"
        )

        self.window._export_single_asset()

        self.assertEqual(Path(get_save.call_args.args[2]).parent, out)


class OverwriteConfirmTests(_DialogDirTests):
    def test_lists_names_that_already_exist(self) -> None:
        out = self.tmp / "dest"
        out.mkdir()
        (out / "a.bundle").write_bytes(b"x")
        (out / "b.bundle").write_bytes(b"x")

        existing = self.vm.existing_destination_names(
            out, ["a.bundle", "b.bundle", "c.bundle"]
        )

        self.assertEqual(existing, ["a.bundle", "b.bundle"])

    @patch("views.save_dialog.QFileDialog.getExistingDirectory", return_value="")
    def test_save_all_cancel_directory_does_not_accept(
        self, _get_dir: MagicMock
    ) -> None:
        dialog = SaveDialog(self.vm)
        dialog._select_output_directory = MagicMock(return_value=False)
        dialog.accept = MagicMock()

        dialog._on_save_all_clicked()

        dialog.accept.assert_not_called()

    @patch("views.save_dialog.confirm_overwrite_existing", return_value=False)
    @patch("views.save_dialog.QFileDialog.getExistingDirectory")
    def test_save_all_overwrite_no_does_not_accept(
        self, get_dir: MagicMock, _confirm: MagicMock
    ) -> None:
        out = self.tmp / "dest"
        out.mkdir()
        (out / "hero.bundle").write_bytes(b"x")
        get_dir.return_value = str(out)
        self.vm.get_source_files = MagicMock(
            return_value=[(str(self._bundle("game")), True)]
        )
        self.vm.has_changed_files = MagicMock(return_value=True)
        dialog = SaveDialog(self.vm)
        dialog.accept = MagicMock()
        received: list[object] = []
        dialog.save_all_requested.connect(lambda *args: received.append(args))

        dialog._on_save_all_clicked()

        dialog.accept.assert_not_called()
        self.assertEqual(received, [])

    @patch("views.main_window.confirm_overwrite_existing", return_value=False)
    @patch("views.main_window.QFileDialog.getExistingDirectory")
    def test_export_multiple_overwrite_no_does_not_export(
        self, get_dir: MagicMock, _confirm: MagicMock
    ) -> None:
        out = self.tmp / "dest"
        out.mkdir()
        (out / "icon.png").write_bytes(b"x")
        get_dir.return_value = str(out)
        window = ABVMEMainWindow(settings=self.settings)
        asset = _asset(str(self._bundle("game")))
        window.viewmodel.selected_assets = [asset]
        window.viewmodel.export_multiple_assets = MagicMock(return_value=(0, 1))

        window._export_multiple_assets()

        window.viewmodel.export_multiple_assets.assert_not_called()
