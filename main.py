from dataclasses import dataclass
from pathlib import Path
from pprint import pprint
from tracemalloc import start
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

@dataclass
class AssetInfo:
    name: str
    container: str
    path_id: str
    type: str
    obj: ObjectReader

class ModMakerCore:
    def __init__(self):
        self._env: Environment
    
    @property
    def loaded_files(self) -> list[str]:
        return list(self._env.files.keys()) if self._env and self._env.files else []

    def load(self, file_list: list[str]):
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
        
    def get_available_assets(self) -> list[AssetInfo]:
        assets = []
        for obj in self._env.objects:
            if obj.type in available_assets:
                assets.append(
                    AssetInfo(
                        obj.peek_name() or "",
                        obj.container or "",
                        str(obj.path_id) or "", 
                        obj.type.name, 
                        obj
                    )
                )
        return assets

    def export(self, obj: ObjectReader, out_path: str | Path):
        obj_data = obj.read()

        if not isinstance(obj_data, (TextAsset, Texture2D, Mesh)):
            raise TypeError("Provided object is not a supported asset type for export.")
        
        container = obj.container
        if container:
            output_name = Path(container).name
            file_name = output_name.split(".")[0]
        else:
            output_name = obj_data.m_Name
            file_name = output_name.split(".")[0] + '_' + str(obj.path_id)
        
        file_extension = ""
        if len(output_name.split(".")) > 1:
            file_extension = "." + output_name.split(".")[1]

        out_path = Path(out_path).resolve()
        out_path.mkdir(parents=True, exist_ok=True)
        if isinstance(obj_data, TextAsset):
            exportTextAsset(obj_data, str(out_path / (file_name)), file_extension)
        elif isinstance(obj_data, Texture2D):
            exportTexture2D(obj_data, str(out_path / (file_name)), file_extension)
        elif isinstance(obj_data, Mesh):
            exportMesh(obj_data, str(out_path / (file_name)), file_extension)

if __name__ == "__main__":
    logging.getLogger().setLevel(logging.DEBUG)
    test = ModMakerCore()
    # test.load(list(filedialog.askopenfilenames()))
    
    from pathlib import Path
    files = list(str(f.resolve().as_posix()) for f in Path("test").rglob("*.bundle"))
    test.load(files)
    # pprint(test._env.files)
    for data in test.get_available_assets():
        test.export(data.obj, "test_output")
        # if isinstance(data.obj, Texture2D):
        #     test.export_Texture2D(
        #         data.obj,
        #         "test_output"
        #     )