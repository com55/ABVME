import ast
import os
import subprocess
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def _run_isolated(script: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [str(_ROOT), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _loaded_unitypy_modules() -> str:
    return (
        "loaded = [n for n in sys.modules "
        'if n == "UnityPy" or n.startswith("UnityPy.")]'
    )


class MainStartupImportTests(unittest.TestCase):
    def test_window_import_is_deferred_until_after_coalesce(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "main.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)
        top_level: list[str] = []
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.module:
                top_level.append(node.module)
            elif isinstance(node, ast.Import):
                top_level.extend(alias.name for alias in node.names)

        self.assertFalse(
            any(name == "views" or name.startswith("views.") for name in top_level),
            f"views must not be imported before coalesce, got {top_level}",
        )
        self.assertFalse(
            any(name == "models" or name.startswith("models.") for name in top_level),
            f"models/UnityPy must not be imported before coalesce, got {top_level}",
        )
        self.assertNotIn("utilities", top_level)

    def test_importing_main_window_does_not_load_unitypy(self) -> None:
        result = _run_isolated(
            "import sys\n"
            "from PySide6.QtWidgets import QApplication\n"
            "import views.main_window as mw\n"
            "app = QApplication([])\n"
            "window = mw.ABVMEMainWindow()\n"
            f"{_loaded_unitypy_modules()}\n"
            "assert not loaded, loaded\n"
            "assert window is not None\n"
            "assert app is not None\n"
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_load_files_imports_unitypy(self) -> None:
        result = _run_isolated(
            "import sys\n"
            "from models.core_model import ABVMECore\n"
            f"{_loaded_unitypy_modules()}\n"
            "assert not loaded, loaded\n"
            "core = ABVMECore()\n"
            f"{_loaded_unitypy_modules()}\n"
            "assert not loaded, loaded\n"
            "core.load_files([])\n"
            f"{_loaded_unitypy_modules()}\n"
            "assert loaded, 'load_files must import UnityPy'\n"
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
