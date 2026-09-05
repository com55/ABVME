"""
Asset Model Layer - MVVM Pattern
Contains data structures and business logic for assets
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from functools import cache
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, BinaryIO, Callable, Optional

from PIL import Image as PILImage
from PIL.Image import Image

from .save_options import StreamCapture

if TYPE_CHECKING:
    from UnityPy.enums import ClassIDType
    from UnityPy.files import ObjectReader


@cache
def _unity() -> SimpleNamespace:
    """Import UnityPy on first asset use, not when the window module loads."""
    from UnityPy.classes import Mesh, TextAsset, Texture2D
    from UnityPy.enums import ClassIDType
    from UnityPy.tools.extractor import exportMesh, exportTextAsset, exportTexture2D

    edit_types = (ClassIDType.Texture2D, ClassIDType.TextAsset)
    return SimpleNamespace(
        Texture2D=Texture2D,
        TextAsset=TextAsset,
        Mesh=Mesh,
        ClassIDType=ClassIDType,
        exportTextAsset=exportTextAsset,
        exportTexture2D=exportTexture2D,
        exportMesh=exportMesh,
        edit_types=edit_types,
        export_types=edit_types,
    )


def warmup_unitypy() -> None:
    """Import the UnityPy modules used on first file open."""
    from UnityPy import Environment  # noqa: F401

    _unity()


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


_DUMP_MAX_CHARS = 200_000
_DUMP_MAX_ITEMS = 80
_DUMP_MAX_DEPTH = 8
_DUMP_MAX_STR = 400
_DUMP_INDENT = "      "
EMPTY_CELL_TEXT = "(none)"


def format_byte_size(n: int) -> str:
    """Format a byte count as 1024-based human-readable text."""
    if n < 1024:
        return f"{n} B"
    value = float(n)
    units = ("KB", "MB", "GB", "TB")
    for i, unit in enumerate(units):
        value /= 1024.0
        rounded = round(value, 1)
        if rounded < 1024.0 or i == len(units) - 1:
            return f"{rounded:.1f} {unit}"
    raise RuntimeError("format_byte_size: unit loop exhausted")


def format_object_dump(value: Any, *, max_chars: int = _DUMP_MAX_CHARS) -> str:
    """Format a parsed Unity object for the Dump tab, with size limits."""

    def fmt(item: Any, depth: int) -> str:
        if depth >= _DUMP_MAX_DEPTH:
            return "<...>"
        if isinstance(item, bytes):
            if not item:
                return "None"
            return "<bytes data>"
        if isinstance(item, str):
            if len(item) > _DUMP_MAX_STR:
                return f'"{item[:_DUMP_MAX_STR]}..."'
            return f'"{item}"'
        if isinstance(item, dict):
            if not item:
                return "{}"
            keys = list(item.keys())
            extra = len(keys) - _DUMP_MAX_ITEMS
            shown = keys[:_DUMP_MAX_ITEMS]
            pad = _DUMP_INDENT * depth
            next_pad = _DUMP_INDENT * (depth + 1)
            lines = [
                f"{next_pad}{key} = {fmt(item[key], depth + 1).lstrip()}"
                for key in shown
            ]
            if extra > 0:
                lines.append(f"{next_pad}<+{extra} more>")
            return "{\n" + "\n".join(lines) + f"\n{pad}}}"
        if isinstance(item, (list, tuple)):
            brackets = ("(", ")") if isinstance(item, tuple) else ("[", "]")
            if not item:
                return f"{brackets[0]}{brackets[1]}"
            extra = len(item) - _DUMP_MAX_ITEMS
            shown = item[:_DUMP_MAX_ITEMS]
            pad = _DUMP_INDENT * depth
            next_pad = _DUMP_INDENT * (depth + 1)
            lines = [f"{next_pad}{fmt(entry, depth + 1).lstrip()}" for entry in shown]
            if extra > 0:
                lines.append(f"{next_pad}<+{extra} more>")
            return f"{brackets[0]}\n" + "\n".join(lines) + f"\n{pad}{brackets[1]}"
        return str(item)

    text = fmt(value, 0)
    if len(text) > max_chars:
        return text[:max_chars] + "\n<truncated>"
    return text


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


def planned_export_parts(
    *,
    name: str,
    container: str,
    path_id: str,
    output_name: str | None = None,
) -> tuple[str, str]:
    """Return (file_name_without_ext, suffix_with_dot) used by export."""
    need_to_add_path_id = False
    if output_name:
        full_name = output_name
    elif container:
        full_name = Path(container).name
    else:
        full_name = name
        need_to_add_path_id = True

    parts = full_name.split(".")
    file_name = parts[0]
    if need_to_add_path_id:
        file_name += "_" + str(path_id)
    file_extension = f".{parts[1]}" if len(parts) > 1 else ""
    return file_name, file_extension


def planned_export_filename(
    *,
    name: str,
    container: str,
    path_id: str,
    output_name: str | None = None,
) -> str:
    file_name, file_extension = planned_export_parts(
        name=name,
        container=container,
        path_id=path_id,
        output_name=output_name,
    )
    return f"{file_name}{file_extension}"


class AssetInfo:
    """
    Asset information and operations wrapper
    Encapsulates UnityPy ObjectReader with high-level operations
    """

    def __init__(
        self,
        obj: ObjectReader[Any],
        source_path: str = "",
        register_stream_capture: Callable[[str, int, StreamCapture], None]
        | None = None,
    ):
        unity = _unity()
        self._obj: ObjectReader[Any] = obj
        self.name: str = self._obj.peek_name() or ""
        self.container: str = self._obj.container or ""
        self.path_id: str = str(self._obj.path_id) or ""
        self.obj_type: ClassIDType = self._obj.type
        self.source_path: str = source_path
        try:
            self.byte_size: int = int(getattr(obj, "byte_size", 0))
        except (TypeError, ValueError):
            self.byte_size = 0
        self.is_changed: bool = False
        self.is_editable: bool = self.obj_type in unity.edit_types
        self.is_exportable: bool = self.obj_type in unity.export_types
        self._readed_data = None
        self._preview_data: Optional[PreviewResult] = None
        self._dump_text: Optional[str] = None
        self._register_stream_capture = register_stream_capture

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
        unity = _unity()

        if (
            isinstance(data, unity.Texture2D)
            and self.obj_type == unity.ClassIDType.Texture2D
        ):
            self._preview_data = PreviewResult(data=data.image, asset_type="Texture2D")
        elif (
            isinstance(data, unity.TextAsset)
            and self.obj_type == unity.ClassIDType.TextAsset
        ):
            self._preview_data = PreviewResult(
                data=data.m_Script, asset_type="TextAsset"
            )
        elif isinstance(data, unity.Mesh) and self.obj_type == unity.ClassIDType.Mesh:
            self._preview_data = PreviewResult(
                data=None,
                asset_type="Mesh",
                status=ResultStatus.UNSUPPORTED,
                message="Preview is unavailable",
            )
        else:
            self._preview_data = PreviewResult(
                data=None,
                asset_type=self.obj_type.name,
                status=ResultStatus.UNSUPPORTED,
                message="Preview is unavailable",
            )
        return self._preview_data

    def get_dump_text(self) -> str:
        """Lazy dump of parse_as_dict(); capped so huge clips do not freeze the UI."""
        if self._dump_text is not None:
            return self._dump_text
        self._dump_text = format_object_dump(self._obj.parse_as_dict())
        return self._dump_text

    def edit_data(self, new_data: Image | str | BinaryIO) -> EditResult:
        """
        Edit asset data with new content
        Supports Texture2D and TextAsset editing
        """
        unity = _unity()
        if not self.is_editable:
            return EditResult(
                status=ResultStatus.UNSUPPORTED,
                message=f"Replace is not supported for {self.obj_type.name}",
            )

        if self.obj_type == unity.ClassIDType.Texture2D:
            self._readed_data = None
            data = self._obj.read()
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
                        message="Unsupported data type for Texture2D editing.",
                    )

                if image_data is None:
                    raise ValueError("Loaded image data is empty.")

                stream = getattr(data, "m_StreamData", None)
                stream_path = getattr(stream, "path", "") if stream is not None else ""
                capture = None
                if stream_path and self.source_path and self._register_stream_capture:
                    capture = StreamCapture(
                        path=str(stream_path),
                        offset=int(getattr(stream, "offset", 0) or 0),
                        size=int(getattr(stream, "size", 0) or 0),
                    )

                data.set_image(image_data)
                data.save()
                raw = getattr(data, "image_data", b"") or b""
                try:
                    image_bytes = bytes(raw)
                except (TypeError, ValueError):
                    image_bytes = b""
                if capture is not None:
                    capture = StreamCapture(
                        path=capture.path,
                        offset=capture.offset,
                        size=capture.size,
                        image_bytes=image_bytes,
                    )
                    self._register_stream_capture(
                        self.source_path,
                        int(self._obj.path_id),
                        capture,
                    )
                elif image_bytes and self.source_path and self._register_stream_capture:
                    self._register_stream_capture(
                        self.source_path,
                        int(self._obj.path_id),
                        StreamCapture(
                            path="",
                            offset=0,
                            size=0,
                            image_bytes=image_bytes,
                        ),
                    )
                self._readed_data = data
                self.is_changed = True
                result = EditResult(
                    status=ResultStatus.COMPLETE,
                    data=data.image,
                    message="Texture2D replaced successfully.",
                )
            except Exception as e:
                return EditResult(
                    status=ResultStatus.ERROR,
                    data=data.image,
                    error=e,
                    message=f"Failed to save texture: {str(e)}",
                )
        else:
            data = self._get_readed_data()
            if isinstance(data, unity.TextAsset):
                try:
                    if isinstance(new_data, str):
                        if Path(new_data).exists():
                            new_script_data = (
                                Path(new_data)
                                .read_bytes()
                                .decode("utf-8", errors="surrogateescape")
                            )
                        else:
                            new_script_data = new_data
                    elif isinstance(new_data, BinaryIO):
                        new_script_data = new_data.read().decode(
                            "utf-8", errors="surrogateescape"
                        )
                    else:
                        result = EditResult(
                            status=ResultStatus.ERROR,
                            data=data.m_Script,
                            error=ValueError("Unsupported data type"),
                            message="Unsupported data type",
                        )
                    data.m_Script = new_script_data
                    data.save()
                    self.is_changed = True
                    result = EditResult(
                        status=ResultStatus.COMPLETE,
                        data=data.m_Script,
                        message="TextAsset replaced successfully.",
                    )
                except Exception as e:
                    return EditResult(
                        status=ResultStatus.ERROR,
                        data=data.m_Script,
                        error=e,
                        message=f"Script error: {str(e)}",
                    )
            elif isinstance(data, unity.Mesh):
                return EditResult(
                    status=ResultStatus.NOT_IMPLEMENTED,
                    message="Mesh editing is coming soon!",
                )
            else:
                return EditResult(
                    status=ResultStatus.UNSUPPORTED,
                    message=f"Replace is not supported for {type(data).__name__}",
                )
        if result.is_success:
            self._preview_data = None
            self._dump_text = None
        return result

    def export(
        self, output_dir: str | Path, output_name: Optional[str] = None
    ) -> ExportResult:
        """
        Export asset to file system
        Supports Texture2D, TextAsset, and Mesh export
        """
        obj_data = self._get_readed_data()
        unity = _unity()
        if not isinstance(obj_data, (unity.TextAsset, unity.Texture2D, unity.Mesh)):
            return ExportResult(
                status=ResultStatus.UNSUPPORTED,
                message=f"Export not supported for type: {type(obj_data).__name__}",
            )

        try:
            output_dir = Path(output_dir).resolve()
            output_dir.mkdir(parents=True, exist_ok=True)

            file_name, file_extension = planned_export_parts(
                name=self.name,
                container=self.container,
                path_id=self.path_id,
                output_name=output_name,
            )

            full_path_no_ext = output_dir / file_name

            # Call appropriate export function
            if isinstance(obj_data, unity.TextAsset):
                unity.exportTextAsset(obj_data, str(full_path_no_ext), file_extension)
            elif isinstance(obj_data, unity.Texture2D):
                unity.exportTexture2D(obj_data, str(full_path_no_ext), file_extension)
            elif isinstance(obj_data, unity.Mesh):
                unity.exportMesh(obj_data, str(full_path_no_ext), file_extension)

            final_path = full_path_no_ext.with_suffix(file_extension)

            return ExportResult(
                status=ResultStatus.COMPLETE,
                output_path=final_path,
                message=f"Exported: {file_name}{file_extension}",
            )

        except Exception as e:
            return ExportResult(
                status=ResultStatus.ERROR, message=f"Export failed: {str(e)}"
            )
