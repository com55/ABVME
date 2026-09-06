import ast
import os
import subprocess
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def _run_isolated(script: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(_ROOT), env.get("PYTHONPATH", "")]).rstrip(
        os.pathsep
    )
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
            "import os, sys\n"
            "os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')\n"
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

    def test_showing_window_warms_unitypy_in_background(self) -> None:
        result = _run_isolated(
            "import os, sys\n"
            "os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')\n"
            "from PySide6.QtWidgets import QApplication\n"
            "import views.main_window as mw\n"
            "app = QApplication([])\n"
            "window = mw.ABVMEMainWindow()\n"
            f"{_loaded_unitypy_modules()}\n"
            "assert not loaded, loaded\n"
            "window.show()\n"
            "app.processEvents()\n"
            "thread = window._unitypy_warmup_thread\n"
            "assert thread is not None\n"
            "thread.join(timeout=60)\n"
            "assert not thread.is_alive(), 'warmup thread did not finish'\n"
            f"{_loaded_unitypy_modules()}\n"
            "assert loaded, 'show() must import UnityPy without load_files'\n"
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_showing_window_prewarms_drop_overlay_then_hides_it(self) -> None:
        result = _run_isolated(
            "import os, sys\n"
            "os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')\n"
            "from PySide6.QtWidgets import QApplication\n"
            "import views.main_window as mw\n"
            "app = QApplication([])\n"
            "window = mw.ABVMEMainWindow()\n"
            "assert not window._drop_overlay_warmed\n"
            "assert window.drop_overlay.isHidden()\n"
            "window.show()\n"
            "app.processEvents()\n"
            "assert window._drop_overlay_warmed\n"
            "assert window.drop_overlay.isHidden()\n"
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
