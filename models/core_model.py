"""
Core Model Layer - MVVM Pattern
Contains core business logic for loading and managing Unity assets
"""

import time
import logging
from pathlib import Path
from typing import Literal, Callable, Optional

from UnityPy import Environment
from UnityPy.files import SerializedFile, BundleFile, WebFile
from UnityPy.streams.EndianBinaryReader import EndianBinaryReader

from .asset_model import AssetInfo


# Configure logger
log = logging.getLogger("ABVME")

class ABVMECore:
    """
    Core business logic for ABVME
    Handles loading Unity bundle files and managing assets
    """
    
    def __init__(self):
        self._env: Environment
        self._available_assets: list[AssetInfo] = []
        self._source_paths: list[dict[str, SerializedFile | BundleFile | WebFile | EndianBinaryReader]] = []
    
    @property
    def source_paths(self) -> list[dict[str, SerializedFile | BundleFile | WebFile | EndianBinaryReader]]:
        """Get list of loaded source file paths"""
        if self._source_paths:
            return self._source_paths
        else:
            for path, file in self._env.files.items():
                self._source_paths.append({path: file})
            return self._source_paths

    def load_files(
        self,
        file_list: list[str],
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> list[AssetInfo]:
        """
        Load Unity bundle files from file paths
        
        Args:
            file_list: List of file paths to load
            progress_callback: Optional callback function(current, total, filename) for progress updates
            
        Returns:
            List of AssetInfo objects extracted from bundles
        """
        env = Environment()
        max_try = 100
        total_files = len(file_list)
        log.info(f"Starting to load {total_files} files...")
        
        for idx, file in enumerate(file_list, start=1):
            # Emit progress before loading each file
            if progress_callback:
                progress_callback(idx, total_files, file)
                
            start_time = time.time()
            with open(file, "rb") as f:
                file_byte = f.read()
                
            # Check if file has UnityFS header
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
        """
        Extract available assets from loaded environment
        
        Returns:
            List of AssetInfo objects
        """
        assets = self._available_assets
        bundle_file_dict = {v: k for k, v in self._env.files.items()}
        
        if not assets:
            for obj in self._env.objects:
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
        packer: Literal["lz4", "lzma", "original"] = "original"
    ):
        """
        Save all modified bundle files to output directory
        
        Args:
            output_dir: Output directory path
            packer: Compression method (lz4, lzma, or original)
        """
        start_time = time.time()
        output_dir = Path(output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        saved = 0

        for file in self._env.files.values():
            if not isinstance(file, EndianBinaryReader) and getattr(file, 'is_changed', False):
                output_path = output_dir / file.name
                self._save_fileobj(file, output_path, packer)
                saved += 1
                
        log.info(f"Took {time.time() - start_time:.2f} seconds to save {saved} changed files to {output_dir}")

    def save_file(
        self,
        file: str,
        output_path: str | Path,
        packer: Literal["none", "lz4", "lzma", "original"] = "none"
    ):
        """
        Save a specific bundle file to output path
        
        Args:
            file: File name/path in loaded files
            output_path: Output file path
            packer: Compression method (none, lz4, lzma, or original)
        """
        target_file = self._env.files.get(file)
        if not target_file:
            log.error(f"File {file} not found in loaded files.")
            return

        if not isinstance(target_file, EndianBinaryReader):
            output_path = Path(output_path).resolve()
            self._save_fileobj(target_file, output_path, packer)

    def _save_fileobj(
        self, 
        file_obj: SerializedFile | BundleFile | WebFile, 
        output_path: Path, 
        packer: Literal["none", "lz4", "lzma", "original"] = "none"
    ):
        """Internal helper to save file object to disk"""
        start_time = time.time()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(file_obj.save(packer=packer))
        log.info(f"Took {time.time() - start_time:.2f} seconds to save {output_path}")