import os
import unittest
import uuid

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QDir, QLockFile
from PySide6.QtWidgets import QApplication

from utilities.launch_coalescer import LaunchCoalescer


def _app() -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication([])


class QLockFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _app()

    def _test_lock_path(self) -> str:
        return QDir.tempPath() + f"/abvme_test_{uuid.uuid4().hex}.lock"

    def test_second_try_lock_fails_until_first_unlocks(self) -> None:
        path = self._test_lock_path()
        first = QLockFile(path)
        first.setStaleLockTime(5000)
        second = QLockFile(path)
        second.setStaleLockTime(5000)

        self.assertTrue(first.tryLock(0))
        self.assertFalse(second.tryLock(0))

        first.unlock()
        self.assertTrue(second.tryLock(0))
        second.unlock()


class LaunchCoalescerDrainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _app()

    def test_drain_keeps_waiting_after_consumed_connection(self) -> None:
        coalescer = LaunchCoalescer(
            f"abvme_test_{uuid.uuid4().hex}",
            collection_window_ms=400,
            lock_file_name=f"abvme_test_{uuid.uuid4().hex}.lock",
        )
        waits = [(False, False), (False, True)]
        coalescer.server.waitForNewConnection = lambda _ms: waits.pop(0)
        ticks: list[str] = []
        coalescer._append_from_pending = lambda _collected: ticks.append("tick")

        coalescer._drain_until_quiet([])

        self.assertEqual(waits, [])
        self.assertEqual(ticks, ["tick", "tick"])


if __name__ == "__main__":
    unittest.main()
