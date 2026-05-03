"""
Launch Coalescer - Merges concurrent program launches into one instance.

Selecting multiple files in Windows Explorer and pressing Enter spawns one
process per file. This utility funnels paths from those simultaneous launches
into the first one within a short collection window. Launches that arrive
after the window closes spawn their own independent instances.
"""

import json

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


class LaunchCoalescer(QObject):
    """
    Coalesces file paths from launches that arrive within a short collection
    window into the first launched process. Outside that window, each launch
    runs as its own independent instance with its own window.
    """

    pathsCollected = Signal(list)  # Emitted once with the full batch of paths

    def __init__(self, key: str, collection_window_ms: int = 500):
        super().__init__()
        self.key = key
        self.collection_window_ms = collection_window_ms
        self.server = QLocalServer()
        self._collected: list[str] = []
        self._idle_timer = QTimer()
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self._finish_collection)

    def start(self, file_paths: list[str] | None = None) -> bool:
        """
        Forward `file_paths` to an existing collector if one is open. Otherwise
        become the collector for `collection_window_ms` of idle time.

        Returns:
            True  → caller is the primary; should open a window. `pathsCollected`
                    fires once the window closes with the full batch.
            False → paths were forwarded to another process; caller should exit.
        """
        file_paths = list(file_paths or [])

        if self._forward_to_existing(file_paths):
            return False

        # Become the collector. removeServer clears any stale endpoint left
        # by a prior crashed run.
        QLocalServer.removeServer(self.key)
        if not self.server.listen(self.key):
            # Lost a race against another process that just claimed the role.
            # Retry the forward — by now the winner should be listening.
            if self._forward_to_existing(file_paths):
                return False
            # Couldn't forward and couldn't listen — run standalone.
            self._collected = file_paths
            QTimer.singleShot(0, lambda: self.pathsCollected.emit(self._collected))
            return True

        self.server.newConnection.connect(self._on_new_connection)
        self._collected = file_paths
        self._idle_timer.start(self.collection_window_ms)
        return True

    def _forward_to_existing(self, file_paths: list[str]) -> bool:
        socket = QLocalSocket()
        socket.connectToServer(self.key)
        if not socket.waitForConnected(200):
            socket.abort()
            return False
        try:
            data = json.dumps(file_paths).encode('utf-8')
            socket.write(data)
            socket.flush()
            socket.waitForBytesWritten(500)
            socket.disconnectFromServer()
            if socket.state() != QLocalSocket.LocalSocketState.UnconnectedState:
                socket.waitForDisconnected(500)
        finally:
            socket.close()
        return True

    def _on_new_connection(self):
        socket = self.server.nextPendingConnection()
        if not socket:
            return
        if socket.waitForReadyRead(500):
            data = bytes(socket.readAll().data())
            try:
                paths = json.loads(data.decode('utf-8'))
                if isinstance(paths, list):
                    self._collected.extend(p for p in paths if isinstance(p, str))
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass
        socket.close()
        # Each new arrival extends the window so a steady drip of launches
        # all batch together.
        self._idle_timer.start(self.collection_window_ms)

    def _finish_collection(self):
        # Stop accepting new launches into this batch — future launches will
        # find no collector and start their own instances.
        self.server.close()
        self.pathsCollected.emit(self._collected)
