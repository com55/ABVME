import os
import unittest
import uuid

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QDir, QLockFile
from PySide6.QtWidgets import QApplication


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


if __name__ == "__main__":
    unittest.main()
