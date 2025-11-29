"""
Single Instance - Utility for ensuring only one app instance runs
"""

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


class SingleInstance(QObject):
    """
    Ensures only one instance of the application runs
    If another instance tries to start, signals the existing one
    """
    messageReceived = Signal()

    def __init__(self, key: str):
        super().__init__()
        self.key = key
        self.server = QLocalServer()

    def start(self):
        """
        Start listening for other instances
        Returns True if this is the first instance, False otherwise
        """
        result = self.server.listen(self.key)

        # If listen failed, another instance exists
        if not result:
            self._notify_existing_instance()
            return False
        
        # Normal mode - wait for connections from other instances
        self.server.newConnection.connect(self._handle_connection)
        return True

    def _notify_existing_instance(self):
        """Send signal to existing instance to bring window to front"""
        socket = QLocalSocket()
        socket.connectToServer(self.key)
        if socket.waitForConnected(500):
            socket.write(b"activate")
            socket.flush()
            socket.waitForBytesWritten(500)
        socket.close()

    def _handle_connection(self):
        """Handle connection from new instance attempt"""
        socket = self.server.nextPendingConnection()
        if socket:
            socket.readAll()
            socket.close()
        self.messageReceived.emit()

