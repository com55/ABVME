"""
Loader Worker - Background thread for loading bundle files
"""

from PySide6.QtCore import QThread, Signal

from models import ABVMECore


class LoaderWorker(QThread):
    """
    Background worker for loading Unity bundle files
    Emits finished signal with list of loaded assets
    """
    progress = Signal(int, int, str)  # Signal: (current, total, filename) files loaded
    finished = Signal(list)  # Signal to emit when loading is complete
    
    def __init__(self, core: ABVMECore, files: list[str]):
        super().__init__()
        self.core = core or ABVMECore()
        self.files = files
    
    def run(self):
        """Execute loading in background thread"""
        def on_progress(current: int, total: int, filename: str):
            self.progress.emit(current, total, filename)
        
        assets = self.core.load_files(self.files, progress_callback=on_progress)
        self.finished.emit(assets)

