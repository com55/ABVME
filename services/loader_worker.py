"""
Loader Worker - Background thread for loading bundle files
"""

from PySide6.QtCore import QThread, Signal

from models import AssetBundlesEditorCore, AssetInfo


class LoaderWorker(QThread):
    """
    Background worker for loading Unity bundle files
    Emits finished signal with list of loaded assets
    """
    finished = Signal(list)  # Signal to emit when loading is complete
    
    def __init__(self, core: AssetBundlesEditorCore, files: list[str]):
        super().__init__()
        self.core = core or AssetBundlesEditorCore()
        self.files = files
    
    def run(self):
        """Execute loading in background thread"""
        assets = self.core.load_files(self.files)
        self.finished.emit(assets)

