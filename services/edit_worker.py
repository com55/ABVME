"""
Edit Worker - Background thread for editing assets
"""

from PySide6.QtCore import QThread, Signal

from models import AssetInfo, EditResult, ResultStatus
from models.texture_replace_options import TextureReplaceOptions


class EditWorker(QThread):
    """
    Background worker for editing asset data
    Emits finished signal with asset and result
    """

    finished = Signal(object, object)  # asset, result

    def __init__(
        self,
        asset: AssetInfo,
        source: str,
        texture_options: TextureReplaceOptions | None = None,
    ):
        super().__init__()
        self.asset = asset
        self.source = source
        self.texture_options = texture_options

    def run(self):
        """Execute editing in background thread"""
        try:
            result = self.asset.edit_data(
                self.source, texture_options=self.texture_options
            )
        except Exception as exc:
            result = EditResult(
                status=ResultStatus.ERROR,
                message=f"Edit failed: {exc}",
                error=exc,
            )
        self.finished.emit(self.asset, result)
