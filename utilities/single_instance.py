"""
Single Instance - Utility for ensuring only one app instance runs
"""

import json

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


class SingleInstance(QObject):
    """
    Ensures only one instance of the application runs
    If another instance tries to start, signals the existing one
    """
    messageReceived = Signal(list)  # List of file paths

    def __init__(self, key: str):
        super().__init__()
        self.key = key
        self.server = QLocalServer()
        self._file_paths: list[str] = []

    def start(self, file_paths: list[str] | None = None) -> bool:
        """
        Start listening for other instances
        
        Args:
            file_paths: Optional list of file paths to send to existing instance
            
        Returns:
            True if this is the first instance, False otherwise
        """
        self._file_paths = file_paths or []
        result = self.server.listen(self.key)

        # If listen failed, another instance exists
        if not result:
            self._notify_existing_instance(self._file_paths)
            return False
        
        # Normal mode - wait for connections from other instances
        self.server.newConnection.connect(self._handle_connection)
        return True

    def _notify_existing_instance(self, file_paths: list[str]):
        """
        Send file paths to existing instance
        
        Args:
            file_paths: List of file paths to send
        """
        socket = QLocalSocket()
        socket.connectToServer(self.key)
        if socket.waitForConnected(500):
            # Encode file paths as JSON
            data = json.dumps(file_paths).encode('utf-8')
            socket.write(data)
            socket.flush()
            socket.waitForBytesWritten(500)
        socket.close()

    def _handle_connection(self):
        """Handle connection from new instance attempt"""
        socket = self.server.nextPendingConnection()
        if socket:
            # Wait for data to arrive
            if socket.waitForReadyRead(500):
                data = bytes(socket.readAll().data())
                try:
                    file_paths = json.loads(data.decode('utf-8'))
                    if not isinstance(file_paths, list):
                        file_paths = []
                except (json.JSONDecodeError, UnicodeDecodeError):
                    file_paths = []
            else:
                file_paths = []
            socket.close()
            self.messageReceived.emit(file_paths)
