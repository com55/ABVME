"""
Edit Worker - Background thread for editing assets
"""

from PySide6.QtCore import QThread, Signal

from models import AssetInfo, EditResult, ResultStatus


class EditWorker(QThread):
    """
    Background worker for editing asset data
    Emits finished signal with asset and result
    """
    finished = Signal(object, object)  # asset, result

    def __init__(self, asset: AssetInfo, source: str):
        super().__init__()
        self.asset = asset
        self.source = source

    def run(self):
        """Execute editing in background thread"""
        try:
            result = self.asset.edit_data(self.source)
        except Exception as exc:
            result = EditResult(
                status=ResultStatus.ERROR,
                message=f"Edit failed: {exc}",
                error=exc,
            )
        self.finished.emit(self.asset, result)

