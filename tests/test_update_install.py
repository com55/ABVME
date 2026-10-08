import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from utilities import update_install as ui


class InstallDetectTests(unittest.TestCase):
    def test_installed_when_exe_in_install_dir(self):
        install = ui.install_dir()
        exe = install / "ABVME.exe"
        with (
            patch.object(ui, "is_running_as_exe", return_value=True),
            patch.object(ui, "get_running_executable_path", return_value=exe),
        ):
            self.assertTrue(ui.is_installed_build())

    def test_portable_when_elsewhere(self):
        with (
            patch.object(ui, "is_running_as_exe", return_value=True),
            patch.object(
                ui,
                "get_running_executable_path",
                return_value=Path("D:/tools/ABVME/ABVME.exe"),
            ),
        ):
            self.assertFalse(ui.is_installed_build())

    def test_silent_args_use_silent_not_verysilent(self):
        args = ui.inno_silent_args(Path("C:/temp/setup.log"))
        joined = " ".join(args)
        self.assertIn("/SILENT", joined)
        self.assertNotIn("/VERYSILENT", joined)

    def test_watcher_waits_for_setup_then_relaunch(self):
        pending = Path("C:/cache/pending.json")
        script = ui.build_relaunch_watcher_ps1(pending, "ABVME-Windows-x64-Setup")
        self.assertIn("Wait-Process -Name $SetupName", script)
        self.assertIn("Start-Process -FilePath $Meta.target_exe_path", script)
        self.assertIn("Test-Path -LiteralPath $Meta.target_exe_path", script)

    def test_launch_uses_shell_execute_for_watcher_and_setup(self):
        calls: list[tuple[str, str, int]] = []

        def fake_shell(
            file: str, params: str, work_dir: str, *, show_cmd: int = 1
        ) -> None:
            calls.append((file, params, show_cmd))

        with tempfile.TemporaryDirectory() as tmp:
            setup = Path(tmp) / "ABVME-Windows-x64-Setup.exe"
            setup.write_bytes(b"mz")
            target = Path(tmp) / "ABVME.exe"
            target.write_bytes(b"mz")
            with (
                patch.object(ui, "update_cache_dir", return_value=Path(tmp)),
                patch.object(ui, "_shell_execute", side_effect=fake_shell),
                patch.object(ui, "strip_motw"),
            ):
                ui.launch_setup_and_prepare_relaunch(setup, target, [])

        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][0].lower(), "powershell.exe")
        self.assertIn("-WindowStyle Hidden", calls[0][1])
        self.assertIn("-File ", calls[0][1])
        self.assertEqual(calls[0][2], 0)
        self.assertEqual(Path(calls[1][0]), setup)
        self.assertIn("/SILENT", calls[1][1])
        self.assertEqual(calls[1][2], 1)


if __name__ == "__main__":
    unittest.main()
