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


if __name__ == "__main__":
    unittest.main()
