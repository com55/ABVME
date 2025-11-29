"""
File Drop Widget - Drag & Drop file handler
"""

from typing import Callable, Optional
from PySide6.QtCore import Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QWidget


class FileDropWidget(QWidget):
    """
    Widget that accepts drag & drop of files
    Can be used as a base widget for panels that accept file drops
    """
    files_dropped = Signal(list)

    def __init__(
        self, 
        parent=None, 
        drop_handler: Optional[Callable[[list[str]], bool]] = None, 
        can_accept_drop: Optional[Callable[[], bool]] = None
    ):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.drop_handler = drop_handler
        self.can_accept_drop = can_accept_drop

    def _can_accept(self) -> bool:
        """Check if widget can currently accept drops"""
        if self.can_accept_drop:
            return self.can_accept_drop()
        return True

    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle drag enter event"""
        if not event.mimeData().hasUrls():
            event.ignore()
            return

        urls = event.mimeData().urls()
        if not any(url.isLocalFile() for url in urls):
            event.ignore()
            return

        if not self._can_accept():
            event.ignore()
            return

        event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        """Handle drop event"""
        urls = event.mimeData().urls()
        paths = [str(url.toLocalFile()) for url in urls if url.isLocalFile()]
        if not paths or not self._can_accept():
            event.ignore()
            return

        accepted = False
        if self.drop_handler:
            accepted = self.drop_handler(paths)
        else:
            self.files_dropped.emit(paths)
            accepted = True

        if accepted:
            event.acceptProposedAction()
        else:
            event.ignore()

