"""
Asset Model Layer - MVVM Pattern
Contains data structures and business logic for assets
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, BinaryIO, Optional, Union

from PIL import Image as PILImage
from PIL.Image import Image
from UnityPy.classes import Texture2D, TextAsset, Mesh
from UnityPy.files import ObjectReader
from UnityPy.enums import ClassIDType
from UnityPy.tools.extractor import exportTextAsset, exportTexture2D, exportMesh


class ResultStatus(str, Enum):
    """Status of operation results"""
    COMPLETE = "COMPLETE"
    ERROR = "ERROR"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass
class PreviewResult:
    """Result of asset preview generation"""
    data: Image | str | None
    asset_type: str
    status: ResultStatus = ResultStatus.COMPLETE
    message: str = ""

    @property
    def has_preview(self) -> bool:
        """Check if preview is available"""
        return self.data is not None and self.status == ResultStatus.COMPLETE


@dataclass
class EditResult:
    """Result of asset editing operation"""
    status: ResultStatus
    data: Any = None
    error: Optional[Exception] = None
    message: str = ""

    @property
    def is_success(self) -> bool:
        """Check if operation was successful"""
        return self.status == ResultStatus.COMPLETE


@dataclass
class ExportResult:
    """Result of asset export operation"""
    status: ResultStatus
    output_path: Optional[Path] = None
    message: str = ""
    
    @property
    def is_success(self) -> bool:
        """Check if operation was successful"""
        return self.status == ResultStatus.COMPLETE


class AssetInfo:
    """
    Asset information and operations wrapper
    Encapsulates UnityPy ObjectReader with high-level operations
    """
    
    def __init__(self, obj: ObjectReader, source_path: str = ""):
        self._obj: ObjectReader = obj
        self.name: str = self._obj.peek_name() or ""
        self.container: str = self._obj.container or ""
        self.path_id: str = str(self._obj.path_id) or ""
        self.obj_type: ClassIDType = self._obj.type
        self.source_path: str = source_path
        self.is_changed: bool = False
        self._readed_data = None

    def _get_readed_data(self):
        """Lazy load and cache asset data"""
        if self._readed_data:
            return self._readed_data
        else:
            self._readed_data = self._obj.read()
            return self._readed_data
    
    def get_preview(self) -> PreviewResult:
        """
        Generate preview data for the asset
        Returns appropriate data type based on asset type
        """
        data = self._get_readed_data()

        if isinstance(data, Texture2D):
            return PreviewResult(data=data.image, asset_type="Texture2D")
        elif isinstance(data, TextAsset):
            return PreviewResult(data=data.m_Script, asset_type="TextAsset")
        elif isinstance(data, Mesh):
            return PreviewResult(data=data.export(), asset_type="Mesh")
        else:
            return PreviewResult(
                data=None, 
                asset_type=type(data).__name__,
                status=ResultStatus.UNSUPPORTED,
                message="Preview not available for this asset type"
            )

    def edit_data(self, new_data: Image | str | BinaryIO) -> EditResult:
        """
        Edit asset data with new content
        Supports Texture2D and TextAsset editing
        """
        data = self._get_readed_data()
        
        if isinstance(data, Texture2D):
            try:
                image_data = None
                if isinstance(new_data, Image):
                    image_data = new_data
                elif isinstance(new_data, (str, Path)):
                    with PILImage.open(new_data) as img:
                        image_data = img.copy()
                elif isinstance(new_data, BinaryIO):
                    with PILImage.open(new_data) as img:
                        image_data = img.copy()
                else:
                    return EditResult(
                        status=ResultStatus.ERROR,
                        data=data.image,
                        error=TypeError("Unsupported data type for Texture2D"),
                        message="Unsupported data type for Texture2D editing."
                    )

                if image_data is None:
                    raise ValueError("Loaded image data is empty.")

                data.set_image(image_data)
                data.save()
                self.is_changed = True
                return EditResult(
                    status=ResultStatus.COMPLETE, 
                    data=data.image,
                    message="Texture2D updated successfully."
                )
            except Exception as e:
                return EditResult(
                    status=ResultStatus.ERROR, 
                    data=data.image,
                    error=e,
                    message=f"Failed to save texture: {str(e)}"
                )
                
        elif isinstance(data, TextAsset):
            try:
                if isinstance(new_data, str):
                    if Path(new_data).exists():
                        new_script_data = Path(new_data).read_bytes().decode("utf-8", errors="surrogateescape")
                    else:
                        new_script_data = new_data
                elif isinstance(new_data, BinaryIO):
                    new_script_data = new_data.read().decode("utf-8", errors="surrogateescape")
                else:
                    return EditResult(
                        status=ResultStatus.ERROR, 
                        data=data.m_Script, 
                        error=ValueError("Unsupported data type"),
                        message="Unsupported data type"
                    )
                data.m_Script = new_script_data
                data.save()
                self.is_changed = True
                return EditResult(
                    status=ResultStatus.COMPLETE, 
                    data=data.m_Script,
                    message="TextAsset updated successfully."
                )
            except Exception as e:
                return EditResult(
                    status=ResultStatus.ERROR, 
                    data=data.m_Script, 
                    error=e,
                    message=f"Script error: {str(e)}"
                )
                
        elif isinstance(data, Mesh):
            return EditResult(
                status=ResultStatus.NOT_IMPLEMENTED, 
                message="Mesh editing is coming soon!"
            )
        else:
            return EditResult(
                status=ResultStatus.UNSUPPORTED, 
                message=f"Editing not supported for {type(data).__name__}"
            )
    
    def export(self, output_dir: str | Path, output_name: Optional[str] = None) -> ExportResult:
        """
        Export asset to file system
        Supports Texture2D, TextAsset, and Mesh export
        """
        obj_data = self._get_readed_data()
        if not isinstance(obj_data, (TextAsset, Texture2D, Mesh)):
            return ExportResult(
                status=ResultStatus.UNSUPPORTED,
                message=f"Export not supported for type: {type(obj_data).__name__}"
            )

        try:
            output_dir = Path(output_dir).resolve()
            output_dir.mkdir(parents=True, exist_ok=True)
            
            need_to_add_path_id = False
            
            if output_name:
                full_name = output_name
            elif self.container:
                full_name = Path(self.container).name
            else:
                full_name = self.name
                need_to_add_path_id = True

            # Split at first dot only
            parts = full_name.split('.') 
            
            file_name = parts[0]
            if need_to_add_path_id:
                file_name += "_" + self.path_id
            
            file_extension = ""
            if len(parts) > 1:
                first_suffix = parts[1]
                file_extension = f".{first_suffix}"

            full_path_no_ext = output_dir / file_name

            # Call appropriate export function
            if isinstance(obj_data, TextAsset):
                exportTextAsset(obj_data, str(full_path_no_ext), file_extension)
            elif isinstance(obj_data, Texture2D):
                exportTexture2D(obj_data, str(full_path_no_ext), file_extension)
            elif isinstance(obj_data, Mesh):
                exportMesh(obj_data, str(full_path_no_ext), file_extension)

            final_path = full_path_no_ext.with_suffix(file_extension)
            
            return ExportResult(
                status=ResultStatus.COMPLETE,
                output_path=final_path,
                message=f"Exported: {file_name}{file_extension}"
            )

        except Exception as e:
            return ExportResult(
                status=ResultStatus.ERROR,
                message=f"Export failed: {str(e)}"
            )


