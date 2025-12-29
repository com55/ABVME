"""
Asset Model Layer - MVVM Pattern
Contains data structures and business logic for assets
"""

from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
from typing import Any, BinaryIO, Optional

from PIL import Image as PILImage
from PIL.Image import Image
from UnityPy.classes import Texture2D, TextAsset, Mesh
from UnityPy.files import ObjectReader
from UnityPy.enums import ClassIDType
from UnityPy.tools.extractor import exportTextAsset, exportTexture2D, exportMesh

AVAILABLE_ASSETS_FOR_EDIT = [
    ClassIDType.Texture2D, 
    ClassIDType.TextAsset, 
    # ClassIDType.Mesh
]

AVAILABLE_ASSETS_FOR_EXPORT = [
    ClassIDType.Texture2D, 
    ClassIDType.TextAsset, 
    # ClassIDType.Mesh,
]

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
    parsed_data: str = ""
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
    
    def __init__(self, obj: ObjectReader[Any], source_path: str = ""):
        self._obj: ObjectReader[Any] = obj
        self.name: str = self._obj.peek_name() or ""
        self.container: str = self._obj.container or ""
        self.path_id: str = str(self._obj.path_id) or ""
        self.obj_type: ClassIDType = self._obj.type
        self.source_path: str = source_path
        self.is_changed: bool = False
        self.is_editable: bool = self.obj_type in AVAILABLE_ASSETS_FOR_EDIT
        self.is_exportable: bool = self.obj_type in AVAILABLE_ASSETS_FOR_EXPORT
        self._readed_data = None
        self._preview_data: Optional[PreviewResult] = None

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
        if self._preview_data:
            return self._preview_data
        
        data = self._get_readed_data()
        
        INDENT = "      "
        
        def fmt(value: Any, indent: int = 0) -> str:
            """Recursively format any value to readable string"""
            pad = INDENT * indent
            next_pad = INDENT * (indent + 1)
            
            if isinstance(value, bytes):
                # return f'"{value.decode("utf-8", errors="surrogateescape")}"'
                return f"<bytes data>"
            elif isinstance(value, str):
                return f'"{value}"'
            elif isinstance(value, dict):
                if not value:
                    return "{}"
                lines = [f"{next_pad}{k} = {fmt(v, indent + 1).lstrip()}" for k, v in value.items()]
                return "{\n" + "\n".join(lines) + f"\n{pad}}}"
            elif isinstance(value, (list, tuple)):
                if not value:
                    return "()" if isinstance(value, tuple) else "[]"
                brackets = ("(", ")") if isinstance(value, tuple) else ("[", "]")
                lines = [f"{next_pad}{fmt(item, indent + 1).lstrip()}" for item in value]
                return f"{brackets[0]}\n" + "\n".join(lines) + f"\n{pad}{brackets[1]}"
            else:
                return str(value)
        
        parsed_data = fmt(self._obj.parse_as_dict())
        
        if isinstance(data, Texture2D) and self.obj_type == ClassIDType.Texture2D:
            self._preview_data = PreviewResult(data=data.image, asset_type="Texture2D", parsed_data=parsed_data)
        elif isinstance(data, TextAsset) and self.obj_type == ClassIDType.TextAsset:
            self._preview_data = PreviewResult(data=data.m_Script, asset_type="TextAsset", parsed_data=parsed_data)
        elif isinstance(data, Mesh) and self.obj_type == ClassIDType.Mesh:
            self._preview_data = PreviewResult(data=data.export(), asset_type="Mesh", parsed_data=parsed_data)
        else:
            self._preview_data = PreviewResult(
                data=None, 
                asset_type=self.obj_type.name,
                status=ResultStatus.UNSUPPORTED,
                parsed_data=parsed_data,
                message="Preview not available for this asset type"
            )
        return self._preview_data

    def edit_data(self, new_data: Image | str | BinaryIO) -> EditResult:
        """
        Edit asset data with new content
        Supports Texture2D and TextAsset editing
        """
        data = self._get_readed_data()
        if not self.is_editable:
            return EditResult(
                status=ResultStatus.UNSUPPORTED,
                message=f"Editing not supported for {self.obj_type.name}"
            )

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
                result = EditResult(
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
                    result = EditResult(
                        status=ResultStatus.ERROR, 
                        data=data.m_Script, 
                        error=ValueError("Unsupported data type"),
                        message="Unsupported data type"
                    )
                data.m_Script = new_script_data
                data.save()
                self.is_changed = True
                result = EditResult(
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
        if result.is_success:
            self._preview_data = None
        return result
    
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


