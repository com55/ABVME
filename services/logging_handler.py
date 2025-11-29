"""
Logging Handler - Custom handler for routing logs to UI
"""

import logging
from PySide6.QtCore import SignalInstance


class StatusBarHandler(logging.Handler):
    """
    Custom logging handler that forwards log messages to UI via Qt Signal
    Thread-safe way to display logs in status bar
    """
    
    def __init__(self, signal: SignalInstance):
        super().__init__()
        self.signal = signal
        
        # Set formatter
        formatter = logging.Formatter('%(message)s')
        self.setFormatter(formatter)

    def emit(self, record):
        """Emit log record to UI via signal"""
        msg = self.format(record)
        # Forward to UI through Signal (thread-safe)
        self.signal.emit(msg, record.levelno)

