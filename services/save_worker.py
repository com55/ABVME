"""
Save Worker - Background thread for saving bundle files
"""

import logging
from pathlib import Path
from typing import Literal, Optional

from PySide6.QtCore import QThread, Signal

from models import AssetBundlesEditorCore


log = logging.getLogger("AssetBundlesEditor")


class SaveWorker(QThread):
    """
    Background worker for saving Unity bundle files
    Supports both save all and save single file operations
    """
    # Signals
    progress = Signal(int, int, str)  # current, total, filename
    finished = Signal(bool, str)  # success, message
    error = Signal(str)  # error message
    
    def __init__(
        self, 
        core: AssetBundlesEditorCore,
        output_dir: Path,
        packer: Optional[Literal["lz4", "lzma", "original"]] = None,
        specific_file: Optional[str] = None,
        output_filename: Optional[str] = None
    ):
        """
        Initialize SaveWorker
        
        Args:
            core: AssetBundlesEditorCore instance
            output_dir: Output directory for saved files
            packer: Compression method (lz4, lzma, or original)
            specific_file: If set, save only this file; otherwise save all changed files
            output_filename: Custom output filename (only used with specific_file)
        """
        super().__init__()
        self.core = core
        self.output_dir = Path(output_dir)
        self.packer = packer or "original"
        self.specific_file = specific_file
        self.output_filename = output_filename
    
    def run(self):
        """Execute save operation in background thread"""
        try:
            if self.specific_file:
                # Save single file
                self._save_single_file()
            else:
                # Save all changed files
                self._save_all_files()
        except Exception as e:
            error_msg = f"Save operation failed: {str(e)}"
            log.error(error_msg, exc_info=True)
            self.error.emit(error_msg)
            self.finished.emit(False, error_msg)
    
    def _save_single_file(self):
        """Save a single specific file"""
        try:
            # Use custom filename if provided, otherwise use original
            filename = self.output_filename or Path(self.specific_file).name
            self.progress.emit(1, 1, filename)
            
            # Save the file
            output_path = self.output_dir / filename
            self.core.save_file(self.specific_file, output_path, self.packer)
            
            success_msg = f"Successfully saved {filename}"
            log.info(success_msg)
            self.finished.emit(True, success_msg)
            
        except Exception as e:
            error_msg = f"Failed to save {self.specific_file}: {str(e)}"
            log.error(error_msg)
            raise
    
    def _save_all_files(self):
        """Save all changed files with progress updates"""
        try:
            # Get list of changed files
            changed_files = [
                (path, file) 
                for path, file in self.core._env.files.items()
                if hasattr(file, 'is_changed') and file.is_changed
            ]
            
            total = len(changed_files)
            
            if total == 0:
                msg = "No changed files to save"
                log.info(msg)
                self.finished.emit(True, msg)
                return
            
            # Prepare output directory
            self.output_dir.mkdir(parents=True, exist_ok=True)
            
            # Save each file with progress updates
            saved = 0
            for idx, (path, file_obj) in enumerate(changed_files, 1):
                filename = Path(path).name if hasattr(Path(path), 'name') else getattr(file_obj, 'name', f'file_{idx}')
                
                # Emit progress
                self.progress.emit(idx, total, filename)
                
                # Save file
                output_path = self.output_dir / filename
                self.core._save_fileobj(file_obj, output_path, self.packer)
                saved += 1
                log.info(f"Saved {output_path} ({idx}/{total})")
            
            success_msg = f"Successfully saved {saved} file(s)"
            log.info(success_msg)
            self.finished.emit(True, success_msg)
            
        except Exception as e:
            error_msg = f"Failed during batch save: {str(e)}"
            log.error(error_msg)
            raise

