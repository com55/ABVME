import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from models.core_model import ABVMECore
from models.crc import compute_crc32
from models.save_options import CrcMode, ResourcePatchMode
from services.save_worker import SaveWorker
from viewmodels.main_viewmodel import MainViewModel
from views.main_window import ABVMEMainWindow
from views.save_dialog import SaveDialog


def _fail_load(*_args: object, **_kwargs: object) -> None:
    raise Exception("fail")


def _app() -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication([])


def _file_obj(dataflags: int = 0) -> MagicMock:
    obj = MagicMock()
    obj.save.return_value = b"SAVED"
    obj.dataflags = dataflags
    return obj


def _save(
    core: ABVMECore,
    file_obj: MagicMock,
    output_path: Path,
    *,
    packer: str = "none",
    source_path: str = "bundle",
    original_crc32: int | None = None,
    crc_mode: CrcMode = CrcMode.ON,
    resource_patch_mode: ResourcePatchMode = ResourcePatchMode.INLINE,
) -> list[str]:
    return core._save_fileobj(
        file_obj,
        output_path,
        packer,
        source_path=source_path,
        original_crc32=original_crc32,
        crc_mode=crc_mode,
        resource_patch_mode=resource_patch_mode,
    )


class SaveFileobjCrcTests(unittest.TestCase):
    def setUp(self) -> None:
        self.core = ABVMECore()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.out = Path(self.tmpdir.name) / "out.bundle"

    def test_on_appends_trailer_matching_original_crc(self) -> None:
        desired = compute_crc32(b"load-time-bytes")
        file_obj = _file_obj()
        warnings = _save(self.core, file_obj, self.out, original_crc32=desired)

        out = self.out.read_bytes()
        self.assertEqual(warnings, [])
        self.assertTrue(out.startswith(b"SAVED"))
        self.assertEqual(compute_crc32(out), desired)
        file_obj.save.assert_called_once_with(packer="none")

    def test_overwrite_uses_load_time_crc_not_on_disk_bytes(self) -> None:
        self.out.write_bytes(b"ON-DISK-BYTES-NOT-ORIGINAL")
        desired = compute_crc32(b"load-time-original")
        self.assertNotEqual(compute_crc32(b"ON-DISK-BYTES-NOT-ORIGINAL"), desired)

        warnings = _save(
            self.core,
            _file_obj(),
            self.out,
            source_path=str(self.out),
            original_crc32=desired,
        )

        out = self.out.read_bytes()
        self.assertEqual(warnings, [])
        self.assertTrue(out.startswith(b"SAVED"))
        self.assertEqual(compute_crc32(out), desired)

    def test_auto_windows_applies_crc(self) -> None:
        from UnityPy.enums import BuildTarget
        from UnityPy.files import SerializedFile

        sf = MagicMock(spec=SerializedFile)
        sf.save.return_value = b"SAVED"
        sf.dataflags = 0
        sf.target_platform = BuildTarget.StandaloneWindows64
        desired = compute_crc32(b"windows-original")

        warnings = _save(
            self.core,
            sf,
            self.out,
            original_crc32=desired,
            crc_mode=CrcMode.AUTO,
        )

        out = self.out.read_bytes()
        self.assertEqual(warnings, [])
        self.assertTrue(out.startswith(b"SAVED"))
        self.assertEqual(compute_crc32(out), desired)

    def test_auto_android_skips_crc(self) -> None:
        from UnityPy.enums import BuildTarget
        from UnityPy.files import SerializedFile

        sf = MagicMock(spec=SerializedFile)
        sf.save.return_value = b"SAVED"
        sf.dataflags = 0
        sf.target_platform = BuildTarget.Android

        warnings = _save(
            self.core,
            sf,
            self.out,
            original_crc32=compute_crc32(b"android-original"),
            crc_mode=CrcMode.AUTO,
        )

        self.assertEqual(warnings, [])
        self.assertEqual(self.out.read_bytes(), b"SAVED")

    def test_original_blocks_info_at_end_warns_and_writes_raw(self) -> None:
        file_obj = _file_obj(dataflags=0xC2)
        warnings = _save(
            self.core,
            file_obj,
            self.out,
            packer="original",
            original_crc32=compute_crc32(b"ignored"),
        )

        self.assertTrue(any("CRC not applied" in w for w in warnings))
        self.assertTrue(any("blocks info is at end of file" in w for w in warnings))
        self.assertEqual(self.out.read_bytes(), b"SAVED")

    def test_lz4_name_is_resolved_before_save(self) -> None:
        file_obj = _file_obj()
        _save(
            self.core,
            file_obj,
            self.out,
            packer="lz4",
            crc_mode=CrcMode.OFF,
        )

        file_obj.save.assert_called_once_with(packer=(0x42, 2))
        self.assertEqual(self.out.read_bytes(), b"SAVED")

    def test_crc_corrector_error_warns_and_writes_raw(self) -> None:
        with patch("models.crc.crc_corrector", side_effect=ValueError("crc failed")):
            warnings = _save(
                self.core,
                _file_obj(),
                self.out,
                original_crc32=0x12345678,
            )

        self.assertTrue(any("CRC not applied" in w for w in warnings))
        self.assertEqual(self.out.read_bytes(), b"SAVED")

    def test_stem_fallback_when_overwriting_without_original(self) -> None:
        named = Path(self.tmpdir.name) / "icon_123456.bundle"
        file_obj = _file_obj()
        warnings = _save(
            self.core,
            file_obj,
            named,
            source_path=str(named),
            original_crc32=None,
        )

        self.assertEqual(warnings, [])
        self.assertEqual(compute_crc32(named.read_bytes()), 123456)

    def test_hashes_source_bytes_when_saving_to_another_path(self) -> None:
        source = Path(self.tmpdir.name) / "source.bundle"
        source.write_bytes(b"source-file-bytes")
        desired = compute_crc32(b"source-file-bytes")

        warnings = _save(
            self.core,
            _file_obj(),
            self.out,
            source_path=str(source),
            original_crc32=None,
        )

        self.assertEqual(warnings, [])
        self.assertEqual(compute_crc32(self.out.read_bytes()), desired)

    def test_warns_when_desired_crc_unknown(self) -> None:
        named = Path(self.tmpdir.name) / "no-suffix.bundle"
        warnings = _save(
            self.core,
            _file_obj(),
            named,
            source_path=str(named),
            original_crc32=None,
        )

        self.assertTrue(any(w == "CRC not applied" for w in warnings))
        self.assertEqual(named.read_bytes(), b"SAVED")


class LoadFilesCrcMapTests(unittest.TestCase):
    def test_second_load_drops_first_path_crc_key(self) -> None:
        core = ABVMECore()
        with tempfile.TemporaryDirectory() as td:
            first = Path(td) / "first.bundle"
            second = Path(td) / "second.bundle"
            first.write_bytes(b"UnityFS" + b"\x00" * 16)
            second.write_bytes(b"UnityFS" + b"\x00" * 32)

            with patch("UnityPy.Environment.load_file", side_effect=_fail_load):
                core.load_files([str(first)])
                self.assertEqual(
                    core.original_crc32_for(str(first)),
                    compute_crc32(first.read_bytes()),
                )
                self.assertEqual(core._stream_captures, {})

                core.load_files([str(second)])

            self.assertIsNone(core.original_crc32_for(str(first)))
            self.assertEqual(
                core.original_crc32_for(str(second)),
                compute_crc32(second.read_bytes()),
            )
            self.assertEqual(core._stream_captures, {})

    def test_stores_crc_even_if_load_file_throws(self) -> None:
        core = ABVMECore()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "broken.bundle"
            payload = b"UnityFS" + b"\x00" * 8
            path.write_bytes(payload)
            with patch("UnityPy.Environment.load_file", side_effect=_fail_load):
                core.load_files([str(path)])
            self.assertEqual(core.original_crc32_for(str(path)), compute_crc32(payload))

    def test_save_all_changed_files_removed(self) -> None:
        self.assertFalse(hasattr(ABVMECore, "save_all_changed_files"))


class SaveFileSourcePathTests(unittest.TestCase):
    def test_save_file_forwards_source_path_into_save_fileobj(self) -> None:
        core = ABVMECore()
        source_path = "cab-main"
        file_obj = _file_obj()
        core._env = SimpleNamespace(files={source_path: file_obj})
        captured: dict = {}

        def record(obj, output_path, packer, **kwargs):
            captured["obj"] = obj
            captured["output_path"] = output_path
            captured["packer"] = packer
            captured.update(kwargs)
            return []

        core._save_fileobj = record  # type: ignore[method-assign]
        core._original_crc32 = {source_path: 99}

        core.save_file(source_path, source_path, "original")

        self.assertEqual(captured["source_path"], source_path)
        self.assertEqual(captured["original_crc32"], 99)
        self.assertEqual(captured["packer"], "original")


class SaveWorkerSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _app()

    def test_init_snapshots_modes_and_defaults_packer(self) -> None:
        core = MagicMock()
        worker = SaveWorker(
            core,
            Path("out"),
            packer="",
            resource_patch_mode=ResourcePatchMode.INLINE,
            crc_mode=CrcMode.ON,
        )
        self.assertEqual(worker.packer, "original")
        self.assertEqual(worker.resource_patch_mode, ResourcePatchMode.INLINE)
        self.assertEqual(worker.crc_mode, CrcMode.ON)
        self.assertTrue(hasattr(worker, "warning"))

    def test_save_all_passes_source_path_into_save_fileobj(self) -> None:
        core = MagicMock()
        file_obj = _file_obj()
        file_obj.is_changed = True
        source_path = "cab-main"
        core._env.files = {source_path: file_obj}
        core.original_crc32_for.return_value = 42
        core._save_fileobj.return_value = []

        with tempfile.TemporaryDirectory() as td:
            worker = SaveWorker(
                core,
                Path(td),
                packer="lz4",
                resource_patch_mode=ResourcePatchMode.INLINE,
                crc_mode=CrcMode.ON,
            )
            worker._save_all_files()

        core._save_fileobj.assert_called_once()
        kwargs = core._save_fileobj.call_args.kwargs
        self.assertEqual(kwargs["source_path"], source_path)
        self.assertEqual(kwargs["original_crc32"], 42)
        self.assertEqual(kwargs["crc_mode"], CrcMode.ON)
        self.assertEqual(kwargs["resource_patch_mode"], ResourcePatchMode.INLINE)

    def test_save_file_path_forwards_source_path_and_modes(self) -> None:
        core = MagicMock()
        source_path = "cab-main"
        core.save_file.return_value = []
        with tempfile.TemporaryDirectory() as td:
            worker = SaveWorker(
                core,
                Path(td),
                packer="lz4",
                specific_file=source_path,
                resource_patch_mode=ResourcePatchMode.ORPHAN_CLEANUP,
                crc_mode=CrcMode.OFF,
            )
            worker._save_single_file()

        kwargs = core.save_file.call_args
        self.assertEqual(kwargs.args[0], source_path)
        self.assertEqual(kwargs.kwargs.get("crc_mode"), CrcMode.OFF)
        self.assertEqual(
            kwargs.kwargs.get("resource_patch_mode"),
            ResourcePatchMode.ORPHAN_CLEANUP,
        )

    def test_crc_warning_emitted_and_included_in_finished_message(self) -> None:
        core = MagicMock()
        file_obj = _file_obj()
        file_obj.is_changed = True
        core._env.files = {"cab-main": file_obj}
        core.original_crc32_for.return_value = None
        core._save_fileobj.return_value = [
            "CRC not applied: blocks info is at end of file"
        ]

        seen: list[str] = []
        finished: list[tuple] = []
        with tempfile.TemporaryDirectory() as td:
            worker = SaveWorker(core, Path(td), packer="original")
            worker.warning.connect(seen.append)
            worker.finished.connect(lambda ok, msg: finished.append((ok, msg)))
            worker._save_all_files()

        self.assertEqual(seen, ["CRC not applied: blocks info is at end of file"])
        self.assertEqual(len(finished), 1)
        self.assertTrue(finished[0][0])
        self.assertIn("CRC not applied", finished[0][1])
        self.assertIn("blocks info is at end of file", finished[0][1])

    def test_resource_patch_warning_included_in_finished_message(self) -> None:
        core = MagicMock()
        file_obj = _file_obj()
        file_obj.is_changed = True
        core._env.files = {"cab-main": file_obj}
        core.original_crc32_for.return_value = None
        core._save_fileobj.return_value = [
            "Resource patch: empty image data for cab-x.ress; inlining texture"
        ]

        seen: list[str] = []
        finished: list[tuple] = []
        with tempfile.TemporaryDirectory() as td:
            worker = SaveWorker(core, Path(td), packer="original")
            worker.warning.connect(seen.append)
            worker.finished.connect(lambda ok, msg: finished.append((ok, msg)))
            worker._save_all_files()

        self.assertEqual(
            seen,
            ["Resource patch: empty image data for cab-x.ress; inlining texture"],
        )
        self.assertEqual(len(finished), 1)
        self.assertTrue(finished[0][0])
        self.assertIn("Resource patch:", finished[0][1])
        self.assertIn("inlining texture", finished[0][1])


class SaveWorkerGlueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _app()

    def setUp(self) -> None:
        self.settings = QSettings("ABVMETest", "ABVMESaveFileobjGlue")
        self.settings.clear()
        self.vm = MainViewModel(settings=self.settings)

    def tearDown(self) -> None:
        self.settings.clear()

    @patch("viewmodels.main_viewmodel.SaveWorker")
    def test_save_all_passes_snapshot_kwargs_after_persist(
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

        worker_cls.assert_called_once()
        args, kwargs = worker_cls.call_args
        self.assertEqual(args[2], "lz4")
        self.assertEqual(kwargs["resource_patch_mode"], ResourcePatchMode.INLINE)
        self.assertEqual(kwargs["crc_mode"], CrcMode.ON)
        worker.warning.connect.assert_called()
        self.assertTrue(hasattr(self.vm, "save_warning"))

    @patch("viewmodels.main_viewmodel.SaveWorker")
    def test_omitted_save_kwargs_keep_current_options(
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
        self.vm.set_packer("lz4hc")
        self.vm.set_resource_patch_mode("orphan_cleanup")
        self.vm.set_crc_mode("off")

        self.vm.save_all_files(Path("out"))

        self.assertEqual(self.vm.packer, "lz4hc")
        self.assertEqual(self.vm.resource_patch_mode, ResourcePatchMode.ORPHAN_CLEANUP)
        self.assertEqual(self.vm.crc_mode, CrcMode.OFF)
        self.assertEqual(self.settings.value("packer"), "lz4hc")
        self.assertEqual(self.settings.value("resource_patch_mode"), "orphan_cleanup")
        self.assertEqual(self.settings.value("crc_mode"), "off")
        args, kwargs = worker_cls.call_args
        self.assertEqual(args[2], "lz4hc")
        self.assertEqual(
            kwargs["resource_patch_mode"], ResourcePatchMode.ORPHAN_CLEANUP
        )
        self.assertEqual(kwargs["crc_mode"], CrcMode.OFF)


class SaveFinishDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _app()

    def setUp(self) -> None:
        self.settings = QSettings("ABVMETest", "ABVME")
        self.settings.clear()
        self.vm = MainViewModel(settings=self.settings)

    def tearDown(self) -> None:
        self.settings.clear()

    def test_dialog_uses_warning_when_crc_not_applied(self) -> None:
        dialog = SaveDialog(self.vm)
        self.addCleanup(dialog.close)
        with (
            patch("views.save_dialog.QMessageBox.information") as info,
            patch("views.save_dialog.QMessageBox.warning") as warn,
        ):
            message = "Saved (CRC not applied: blocks info is at end of file)"
            dialog.on_save_finished(True, message)
            info.assert_not_called()
            warn.assert_called_once()
            self.assertIn("blocks info is at end of file", warn.call_args[0][2])

    def test_window_uses_warning_when_crc_not_applied(self) -> None:
        window = ABVMEMainWindow(settings=self.settings)
        self.addCleanup(window.close)
        self.addCleanup(window.deleteLater)
        with (
            patch("views.main_window.QMessageBox.information") as info,
            patch("views.main_window.QMessageBox.warning") as warn,
            patch("views.save_dialog.QMessageBox.information") as dlg_info,
            patch("views.save_dialog.QMessageBox.warning") as dlg_warn,
        ):
            message = (
                "Successfully saved bundle (CRC not applied: "
                "blocks info is at end of file)"
            )
            window._on_save_finished(True, message)
            info.assert_not_called()
            dlg_info.assert_not_called()
            self.assertTrue(warn.called or dlg_warn.called)
            shown = warn.call_args or dlg_warn.call_args
            self.assertIsNotNone(shown)
            self.assertIn("blocks info is at end of file", shown[0][2])

    def test_dialog_uses_warning_when_resource_patch_inlined(self) -> None:
        dialog = SaveDialog(self.vm)
        self.addCleanup(dialog.close)
        with (
            patch("views.save_dialog.QMessageBox.information") as info,
            patch("views.save_dialog.QMessageBox.warning") as warn,
        ):
            message = (
                "Successfully saved bundle (Resource patch: "
                "empty image data for cab-x.ress; inlining texture)"
            )
            dialog.on_save_finished(True, message)
            info.assert_not_called()
            warn.assert_called_once()
            self.assertIn("Resource patch:", warn.call_args[0][2])

    def test_window_uses_warning_when_resource_patch_inlined(self) -> None:
        window = ABVMEMainWindow(settings=self.settings)
        self.addCleanup(window.close)
        self.addCleanup(window.deleteLater)
        with (
            patch("views.main_window.QMessageBox.information") as info,
            patch("views.main_window.QMessageBox.warning") as warn,
            patch("views.save_dialog.QMessageBox.information") as dlg_info,
            patch("views.save_dialog.QMessageBox.warning") as dlg_warn,
        ):
            message = (
                "Successfully saved bundle (Resource patch: "
                "empty image data for cab-x.ress; inlining texture)"
            )
            window._on_save_finished(True, message)
            info.assert_not_called()
            dlg_info.assert_not_called()
            self.assertTrue(warn.called or dlg_warn.called)
            shown = warn.call_args or dlg_warn.call_args
            self.assertIsNotNone(shown)
            self.assertIn("Resource patch:", shown[0][2])


if __name__ == "__main__":
    unittest.main()
