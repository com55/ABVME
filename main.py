from UnityPy.files.SerializedFile import SerializedFile
from UnityPy.files.BundleFile import BundleFile
from UnityPy.files.WebFile import WebFile
from UnityPy.streams.EndianBinaryReader import EndianBinaryReader
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from pprint import pprint
from typing import Any, BinaryIO, Literal, Optional, Union
from PIL import Image as PILImage
from PIL.Image import Image
from UnityPy import Environment
from UnityPy.files import ObjectReader, SerializedFile
from UnityPy.classes import Texture2D, TextAsset, Mesh
from UnityPy.enums import ClassIDType
from UnityPy.tools.extractor import exportTextAsset, exportTexture2D, exportMesh
from tkinter import filedialog
import time
import logging

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s.%(msecs)03d] %(levelname)s (%(filename)s - %(funcName)s): %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger("ModMaker")

available_assets = [
    ClassIDType.Texture2D, 
    ClassIDType.TextAsset, 
    # ClassIDType.Mesh
]

class ResultStatus(str, Enum):
    COMPLETE = "COMPLETE"
    ERROR = "ERROR"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    UNSUPPORTED = "UNSUPPORTED"

@dataclass
class PreviewResult:
    """ผลลัพธ์ของการดึงตัวอย่าง (Preview)"""
    data: Image | str | None
    asset_type: str
    status: ResultStatus = ResultStatus.COMPLETE
    message: str = ""

    @property
    def has_preview(self) -> bool:
        """เช็คว่ามีของให้โชว์ไหม"""
        return self.data is not None and self.status == ResultStatus.COMPLETE

@dataclass
class EditResult:
    """โครงสร้าง Data สำหรับส่งผลลัพธ์กลับไปที่ UI"""
    status: ResultStatus
    data: Any = None
    error: Optional[Exception] = None
    message: str = "" # เพิ่ม message เผื่อส่งข้อความแจ้งเตือนไปโชว์ user

    @property
    def is_success(self) -> bool:
        """Helper function เช็คถ้าง่ายๆ"""
        return self.status == ResultStatus.COMPLETE

@dataclass
class ExportResult:
    status: ResultStatus
    output_path: Optional[Path] = None # ส่ง path เต็มกลับไป เผื่อ UI จะเปิด Folder ให้ user
    message: str = ""
    
    @property
    def is_success(self) -> bool:
        return self.status == ResultStatus.COMPLETE

class AssetInfo:
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
        if self._readed_data:
            return self._readed_data
        else:
            self._readed_data = self._obj.read()
            return self._readed_data
    
    def get_preview(self) -> PreviewResult:
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
                    data=data.image, # ส่งรูปเดิมกลับไปแสดงผล
                    error=e,
                    message=f"Failed to save texture: {str(e)}"
                )
        elif isinstance(data, TextAsset):
            try:
                if isinstance(new_data, str):
                    if Path(new_data).exists():
                        new_script_data = Path(new_data).read_text(encoding="utf-8", errors="surrogateescape")
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
        # 1. เช็ค Type
        obj_data = self._get_readed_data()
        if not isinstance(obj_data, (TextAsset, Texture2D, Mesh)):
            return ExportResult(
                status=ResultStatus.UNSUPPORTED,
                message=f"Export not supported for type: {type(obj_data).__name__}"
            )

        try:
            # 2. เตรียม Path ปลายทาง
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

            # --- CORE LOGIC: Split ที่จุดแรกจุดเดียวพอ ---
            parts = full_name.split('.') 
            
            file_name = parts[0]  # ได้ "archive" จาก "archive.tar.gz"
            if need_to_add_path_id:
                file_name += "_" + self.path_id
            
            file_extension = ""
            if len(parts) > 1:
                first_suffix = parts[1]
                file_extension = f".{first_suffix}"

            # สร้าง Path ปลายทาง (Folder + Filename แบบไม่มี Extension)
            # สาเหตุที่ไม่รวม Extension เพราะ function export ของคุณรับแยกกัน
            full_path_no_ext = output_dir / file_name

            # 4. เรียกฟังก์ชัน Export
            if isinstance(obj_data, TextAsset):
                exportTextAsset(obj_data, str(full_path_no_ext), file_extension)
                
            elif isinstance(obj_data, Texture2D):
                exportTexture2D(obj_data, str(full_path_no_ext), file_extension)
                
            elif isinstance(obj_data, Mesh):
                exportMesh(obj_data, str(full_path_no_ext), file_extension)

            # 5. Return ผลลัพธ์
            # ประกอบร่าง Path เต็มเพื่อส่งคืน UI
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

class ModMakerCore:
    def __init__(self):
        self._env: Environment
        self._available_assets: list[AssetInfo] = []
        self._source_paths: list[dict[str, SerializedFile | BundleFile | WebFile | EndianBinaryReader]] = []
    
    @property
    def source_paths(self) -> list[dict[str, SerializedFile | BundleFile | WebFile | EndianBinaryReader]]:
        if self._source_paths:
            return self._source_paths
        else:
            for path, file in self._env.files.items():
                self._source_paths.append({path: file})
            return self._source_paths

    def load_files(self, file_list: list[str]) -> list[AssetInfo]:
        env = Environment()
        max_try = 100
        log.info(f"Starting to load {len(file_list)} files...")
        for file in file_list:
            start_time = time.time()
            with open(file, "rb") as f:
                file_byte = f.read()
                
            # เช็คว่า file header เป็น UnityFS ไหม
            if len(file_byte) >= 8 and file_byte[:7] != b"UnityFS":
                log.warning(f"File {file} does not have UnityFS header, skipping...")
                continue
            current_trim = 0
            for i in range(max_try):
                try:
                    if current_trim:
                        data = file_byte[:-current_trim]
                        env.load_file(data, name=file)
                        log.debug(f"Trimmed {current_trim} bytes from {file}")
                    else:
                        env.load_file(file)
                    break
                except Exception as e:
                    current_trim += 1
                    if i == max_try - 1:
                        log.error(f"Failed to load {file}: {e}")
            log.info(f"Took {time.time() - start_time:.4f} seconds to load {file}")
        self._env = env
        return self.get_available_assets()

    def get_available_assets(self) -> list[AssetInfo]:
        assets = self._available_assets
        bundle_file_dict = {v: k for k, v in self._env.files.items()}
        if not assets:
            for obj in self._env.objects:
                if obj.type in available_assets:
                    # Find source path
                    source_path = ""
                    target = obj.assets_file
                    if target in bundle_file_dict:
                        source_path = bundle_file_dict[target]
                    elif hasattr(target, "parent") and target.parent in bundle_file_dict:
                        source_path = bundle_file_dict[target.parent]
                    assets.append(AssetInfo(obj, source_path))
        return assets

    def save_all_changed_files(
        self,
        output_dir: str | Path,
        packer: Literal["lz4", "lzma", "original"] | None = None
    ):
        output_dir = Path(output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        effective_packer = packer or "original"

        saved = 0

        for file in self._env.files.values():
            if not isinstance(file, EndianBinaryReader) and file.is_changed:
                output_path = output_dir / file.name
                self._save_fileobj(file, output_path, effective_packer)
                saved += 1
                log.info(f"Saved {output_path}")
        log.info(f"Saved {saved} changed files to {output_dir}")

    def save_file(
        self,
        file: str,
        output_path: str | Path,
        packer: Literal["lz4", "lzma", "original"] | None = None
    ):
        target_file = self._env.files.get(file)
        if not target_file:
            log.error(f"File {file} not found in loaded files.")
            return

        if not isinstance(target_file, EndianBinaryReader):
            output_path = Path(output_path).resolve()
            effective_packer = packer or "original"
            self._save_fileobj(target_file, output_path, effective_packer)
            log.info(f"Saved {output_path}")

    def _save_fileobj(self, file_obj, output_path: Path, packer: str):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(file_obj.save(packer=packer))
        log.info(f"Saved {output_path}")
    
if __name__ == "__main__":
    logging.getLogger().setLevel(logging.DEBUG)
    test = ModMakerCore()
    # test.load(list(filedialog.askopenfilenames()))
    
    from pathlib import Path
    files = list(str(f.resolve().as_posix()) for f in Path("test").rglob("*.bundle"))
    test.load_files(files)
    # pprint(test._env.files)
    # for data in test.get_available_assets():
    #     print(data.name)
    # pprint(test.source_paths)
    # for file in test._env.files.values():
    #     pprint(file.__dict__)