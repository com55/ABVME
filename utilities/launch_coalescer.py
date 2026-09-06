"""
Launch Coalescer - Merges concurrent program launches into one instance.

Selecting multiple files in Windows Explorer and pressing Enter spawns one
process per file. This utility funnels paths from those simultaneous launches
into the first one within a short collection window. Launches that arrive
after the window closes spawn their own independent instances.
"""

import json
import time

from PySide6.QtCore import QDir, QLockFile
from PySide6.QtNetwork import QLocalServer, QLocalSocket

LOCK_FILE_NAME = "ABVME_launch.lock"


class LaunchCoalescer:
    """
    Coalesces file paths from launches that arrive within a short collection
    window into the first launched process. Outside that window, each launch
    runs as its own independent instance with its own window.
    """

    def __init__(
        self,
        key: str,
        collection_window_ms: int = 500,
        *,
        lock_file_name: str = LOCK_FILE_NAME,
        secondary_deadline_ms: int = 20_000,
    ):
        self.key = key
        self.collection_window_ms = collection_window_ms
        self.secondary_deadline_ms = secondary_deadline_ms
        self.server = QLocalServer()
        lock_path = QDir.tempPath() + "/" + lock_file_name
        self._lock = QLockFile(lock_path)
        self._lock.setStaleLockTime(5000)

    def collect(self, file_paths: list[str] | None = None) -> list[str] | None:
        """
        Collect or forward launch paths before any main window is created.

        Returns:
            None  → paths were forwarded to another process; caller should exit.
            list  → full batch of paths; caller should open a window and load them.
        """
        file_paths = list(file_paths or [])

        if self._lock.tryLock(0):
            return self._collect_as_primary(file_paths)

        deadline = time.monotonic() + (self.secondary_deadline_ms / 1000)
        while time.monotonic() < deadline:
            if self._forward_to_existing(file_paths):
                return None
            if self._lock.tryLock(0):
                return self._collect_as_primary(file_paths)
        return file_paths

    def start(self, file_paths: list[str] | None = None) -> list[str] | None:
        """Alias for :meth:`collect` (backward-compatible entry name)."""
        return self.collect(file_paths)

    def _collect_as_primary(self, file_paths: list[str]) -> list[str]:
        collected = list(file_paths)

        QLocalServer.removeServer(self.key)
        self.server.newConnection.connect(
            lambda: self._append_from_pending(collected)
        )

        if not self.server.listen(self.key):
            self._lock.unlock()
            return collected

        self._drain_until_quiet(collected)

        self.server.close()
        self._lock.unlock()
        return collected

    def _drain_until_quiet(self, collected: list[str]) -> None:
        """Block until waitForNewConnection reports a full quiet window.

        `newConnection` may already have consumed the socket, so a False
        `got_conn` is not silence — only `timed_out` ends the drain.
        """
        while True:
            _got_conn, timed_out = self.server.waitForNewConnection(
                self.collection_window_ms
            )
            self._append_from_pending(collected)
            if timed_out:
                break

    def _append_from_pending(self, collected: list[str]) -> None:
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            if not socket:
                continue
            self._read_paths_from_socket(socket, collected)
            socket.close()

    def _forward_to_existing(self, file_paths: list[str]) -> bool:
        socket = QLocalSocket()
        socket.connectToServer(self.key)
        if not socket.waitForConnected(50):
            socket.abort()
            return False
        try:
            data = json.dumps(file_paths).encode("utf-8")
            socket.write(data)
            socket.flush()
            if not socket.waitForBytesWritten(500):
                socket.abort()
                return False
            socket.disconnectFromServer()
            if socket.state() != QLocalSocket.LocalSocketState.UnconnectedState:
                socket.waitForDisconnected(500)
        finally:
            socket.close()
        return True

    def _read_paths_from_socket(
        self, socket: QLocalSocket, collected: list[str]
    ) -> None:
        if socket.waitForReadyRead(500):
            data = bytes(socket.readAll().data())
            try:
                paths = json.loads(data.decode("utf-8"))
                if isinstance(paths, list):
                    collected.extend(p for p in paths if isinstance(p, str))
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass
