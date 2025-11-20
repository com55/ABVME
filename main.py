from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from pprint import pprint
from tracemalloc import start
from typing import Any, Literal, Optional, Union
from PIL.Image import Image
from UnityPy import Environment
from UnityPy.files import ObjectReader
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
    ClassIDType.Mesh
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
    def __init__(self, obj: ObjectReader):
        self._obj: ObjectReader = obj
        self.name: str = self._obj.peek_name() or ""
        self.container: str = self._obj.container or ""
        self.path_id: str = str(self._obj.path_id) or ""
        self.obj_type: ClassIDType = self._obj.type
        self.readed_data = None
    
    def _get_readed_data(self):
        if self.readed_data:
            return self.readed_data
        else:
            self.readed_data = self._obj.read()
            return self.readed_data
    
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
                asset_type=type(data).__name__, # ส่งชื่อ type กลับไปบอกหน่อยว่าเป็นอะไร
                status=ResultStatus.UNSUPPORTED,
                message="Preview not available for this asset type"
            )

    def edit_data(self, new_data) -> EditResult:
        data = self._get_readed_data()
        
        if isinstance(data, Texture2D):
            try:
                data.set_image(new_data)
                data.save()
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
                data.m_Script = new_data
                data.save()
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
    
    def export(self, output_dir: str | Path) -> ExportResult:
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
            if self.container:
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
    
    @property
    def source_paths(self) -> list[str]:
        return list(self._env.files.keys()) if self._env and self._env.files else []

    def load_files(self, file_list: list[str]) -> list[AssetInfo]:
        env = Environment()
        max_try = 100
        log.info(f"Starting to load {len(file_list)} files...")
        for file in file_list:
            start_time = time.time()
            with open(file, "rb") as f:
                file_byte = f.read()
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
            log.info(f"Loaded {file} in {time.time() - start_time:.4f} seconds")
        self._env = env
        return self.get_available_assets()

    def get_available_assets(self) -> list[AssetInfo]:
        assets = self._available_assets
        if not assets:
            for obj in self._env.objects:
                if obj.type in available_assets:
                    assets.append(AssetInfo(obj))
        return assets

if __name__ == "__main__":
    logging.getLogger().setLevel(logging.DEBUG)
    test = ModMakerCore()
    # test.load(list(filedialog.askopenfilenames()))
    
    from pathlib import Path
    files = list(str(f.resolve().as_posix()) for f in Path("test").rglob("*.bundle"))
    test.load_files(files)
    # pprint(test._env.files)
    for data in test.get_available_assets():
        print(data.name)
    pprint(test.source_paths)