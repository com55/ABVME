"""
ABVME Backend Server
FastAPI server providing REST API for Unity Asset Bundle operations
"""

import asyncio
import base64
import io
import logging
import sys
import uuid
from pathlib import Path
from typing import Optional, Literal

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent))

from models import ABVMECore, AssetInfo
from models.asset_model import ResultStatus

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s.%(msecs)03d] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("ABVME")


# ===== Application State =====

class AppState:
    def __init__(self):
        self.core: Optional[ABVMECore] = None
        self.assets: list[AssetInfo] = []

    def reset(self):
        self.core = None
        self.assets = []


state = AppState()

# ===== FastAPI App =====

app = FastAPI(title="ABVME Backend", version="0.1.8")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== Request / Response Models =====

class LoadRequest(BaseModel):
    paths: list[str]


class ExportRequest(BaseModel):
    path_ids: list[str]
    output_dir: str


class ReplaceRequest(BaseModel):
    source_path: str


class SaveRequest(BaseModel):
    output_dir: str
    packer: Literal["none", "lz4", "lzma", "original"] = "none"


# ===== Helpers =====

def get_asset(path_id: str) -> AssetInfo:
    for asset in state.assets:
        if asset.path_id == path_id:
            return asset
    raise HTTPException(status_code=404, detail="Asset not found")


def asset_dict(asset: AssetInfo) -> dict:
    return {
        "path_id": asset.path_id,
        "name": asset.name,
        "container": asset.container,
        "obj_type": asset.obj_type.name,
        "source_path": asset.source_path,
        "is_changed": asset.is_changed,
        "is_editable": asset.is_editable,
        "is_exportable": asset.is_exportable,
    }


# ===== Endpoints =====

@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.8"}


@app.post("/api/reset")
async def reset():
    state.reset()
    return {"status": "ok"}


@app.post("/api/load")
async def load_files(req: LoadRequest):
    if not req.paths:
        raise HTTPException(status_code=400, detail="No paths provided")

    valid = [p for p in req.paths if Path(p).is_file()]
    if not valid:
        raise HTTPException(status_code=400, detail="No valid files found")

    try:
        core = ABVMECore()
        assets = await asyncio.to_thread(core.load_files, valid)
        state.core = core
        state.assets = assets
        return {
            "status": "ok",
            "asset_count": len(assets),
            "file_count": len(valid),
            "assets": [asset_dict(a) for a in assets],
        }
    except Exception as e:
        log.error(f"Load failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/assets")
async def get_assets():
    return {"assets": [asset_dict(a) for a in state.assets]}


@app.get("/api/asset/{path_id}/preview")
async def get_preview(path_id: str):
    asset = get_asset(path_id)
    try:
        preview = await asyncio.to_thread(asset.get_preview)

        if not preview.has_preview:
            return {
                "type": preview.asset_type,
                "status": preview.status.value,
                "message": preview.message,
                "parsed_data": preview.parsed_data,
            }

        if preview.asset_type == "Texture2D" and preview.data is not None:
            buf = io.BytesIO()
            preview.data.save(buf, format="PNG")
            img_b64 = base64.b64encode(buf.getvalue()).decode()
            return {
                "type": "Texture2D",
                "status": "COMPLETE",
                "image": f"data:image/png;base64,{img_b64}",
                "parsed_data": preview.parsed_data,
            }
        elif preview.asset_type == "TextAsset":
            return {
                "type": "TextAsset",
                "status": "COMPLETE",
                "text": preview.data,
                "parsed_data": preview.parsed_data,
            }
        else:
            return {
                "type": preview.asset_type,
                "status": preview.status.value,
                "message": preview.message,
                "parsed_data": preview.parsed_data,
            }
    except Exception as e:
        log.error(f"Preview error {path_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/assets/export")
async def export_assets(req: ExportRequest):
    if not req.path_ids:
        raise HTTPException(status_code=400, detail="No assets selected")

    assets = [a for a in state.assets if a.path_id in req.path_ids]
    if not assets:
        raise HTTPException(status_code=404, detail="No valid assets found")

    output_dir = Path(req.output_dir)
    results = []
    for asset in assets:
        try:
            result = await asyncio.to_thread(asset.export, output_dir)
            results.append({
                "path_id": asset.path_id,
                "name": asset.name,
                "status": result.status.value,
                "output_path": str(result.output_path) if result.output_path else None,
                "message": result.message,
            })
        except Exception as e:
            results.append({
                "path_id": asset.path_id,
                "name": asset.name,
                "status": "ERROR",
                "output_path": None,
                "message": str(e),
            })

    success_count = sum(1 for r in results if r["status"] == "COMPLETE")
    return {"success_count": success_count, "total": len(results), "results": results}


@app.post("/api/asset/{path_id}/replace")
async def replace_asset(path_id: str, req: ReplaceRequest):
    asset = get_asset(path_id)
    if not Path(req.source_path).is_file():
        raise HTTPException(status_code=400, detail="Source file not found")

    try:
        result = await asyncio.to_thread(asset.edit_data, req.source_path)
        return {
            "status": result.status.value,
            "message": result.message,
            "is_success": result.is_success,
        }
    except Exception as e:
        log.error(f"Replace error {path_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/source-files")
async def get_source_files():
    if not state.core or not hasattr(state.core, "_env"):
        return {"files": []}

    files = []
    for path, file_obj in state.core._env.files.items():
        is_changed = hasattr(file_obj, "is_changed") and file_obj.is_changed
        files.append({"path": path, "name": Path(path).name, "is_changed": is_changed})
    return {"files": files}


@app.post("/api/save")
async def save_bundle(req: SaveRequest):
    if not state.core:
        raise HTTPException(status_code=400, detail="No files loaded")

    packer = req.packer if req.packer != "none" else "original"
    try:
        await asyncio.to_thread(
            state.core.save_all_changed_files,
            Path(req.output_dir),
            packer,
        )
        return {"status": "ok", "output_dir": req.output_dir}
    except Exception as e:
        log.error(f"Save error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== Entry Point =====

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ABVME Backend Server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
