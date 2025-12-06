"""
Save Worker - Background thread for saving bundle files
"""

import logging
from pathlib import Path
import time
from typing import Literal, Optional

from PySide6.QtCore import QThread, Signal

from models import ABVMECore


log = logging.getLogger("ABVME")


class SaveWorker(QThread):
    """
    Background worker for saving Unity bundle files
    Supports save all, save single file, and save multiple selected files
    """
    # Signals
    progress = Signal(int, int, str)  # current, total, filename
    finished = Signal(bool, str)  # success, message
    error = Signal(str)  # error message
    
    def __init__(
        self, 
        core: ABVMECore,
        output_dir: Path,
        packer: Literal["none", "lz4", "lzma", "original"] = "none",
        specific_file: Optional[str] = None,
        output_filename: Optional[str] = None,
        specific_files: Optional[list[str]] = None
    ):
        """
        Initialize SaveWorker
        
        Args:
            core: ABVMECore instance
            output_dir: Output directory for saved files
            packer: Compression method (none, lz4, lzma, or original)
            specific_file: If set, save only this file; otherwise save all changed files
            output_filename: Custom output filename (only used with specific_file)
            specific_files: If set, save only these files (list of filepaths)
        """
        super().__init__()
        self.core = core
        self.output_dir = Path(output_dir)
        self.packer: Literal["none", "lz4", "lzma", "original"] = packer or "none"
        self.specific_file = specific_file
        self.output_filename = output_filename
        self.specific_files = specific_files
    
    def run(self):
        """Execute save operation in background thread"""
        try:
            if self.specific_files:
                # Save multiple selected files
                self._save_multiple_files()
            elif self.specific_file:
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
        assert self.specific_file is not None, "specific_file must be set"
        try:
            # Use custom filename if provided, otherwise use original
            filename = self.output_filename or Path(self.specific_file).name
            self.progress.emit(1, 1, filename)
            
            # Save the file
            output_path = self.output_dir / filename
            self.core.save_file(self.specific_file, output_path, self.packer)
            
            success_msg = f"Successfully saved {filename}"
            self.finished.emit(True, success_msg)

        except Exception as e:
            error_msg = f"Failed to save {self.specific_file}: {str(e)}"
            log.error(error_msg)
            raise
            
    def _save_multiple_files(self):
        """Save multiple selected files"""
        assert self.specific_files is not None, "specific_files must be set"
        try:
            start_time = time.time()
            total = len(self.specific_files)
            
            if total == 0:
                msg = "No files to save"
                log.info(msg)
                self.finished.emit(True, msg)
                return
            
            # Prepare output directory
            self.output_dir.mkdir(parents=True, exist_ok=True)
            
            # Save each file with progress updates
            saved = 0
            for idx, filepath in enumerate(self.specific_files, 1):
                filename = Path(filepath).name
                
                # Emit progress
                self.progress.emit(idx, total, filename)
                
                # Save file
                output_path = self.output_dir / filename
                self.core.save_file(filepath, output_path, self.packer)
                saved += 1
            
            success_msg = f"Successfully saved {saved} file(s)"
            log.info(success_msg)
            self.finished.emit(True, success_msg)
            
        except Exception as e:
            error_msg = f"Failed during batch save: {str(e)}"
            log.error(error_msg)
            raise
    
    def _save_all_files(self):
        """Save all changed files with progress updates"""
        try:
            start_time = time.time()
            # Get list of changed files
            changed_files = [
                (path, file) 
                for path, file in self.core._env.files.items()
                if hasattr(file, 'is_changed') and getattr(file, 'is_changed', False)
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
            
            success_msg = f"Successfully saved {saved} file(s)"
            log.info(success_msg)
            self.finished.emit(True, success_msg)
            
        except Exception as e:
            error_msg = f"Failed during batch save: {str(e)}"
            log.error(error_msg)
            raise

