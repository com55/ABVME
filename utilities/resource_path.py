"""
Resource Path Utility
Handles resource path resolution for both development and compiled (Nuitka) environments
"""

import sys
from pathlib import Path


def get_base_path() -> Path:
    """
    Get the base path for resources.
    
    Returns:
        Path to the application's base directory.
        - In development: the directory containing the source files
        - In compiled mode: the directory containing the executable
    """
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        return Path(sys.executable).parent
    else:
        # Running in development
        return Path(__file__).parent.parent


def get_resource_path(relative_path: str) -> Path:
    """
    Get absolute path to a resource file.
    
    Args:
        relative_path: Path relative to the application's base directory
        
    Returns:
        Absolute Path object to the resource
        
    Example:
        >>> get_resource_path("styles.qss")
        Path('/path/to/app/styles.qss')
        >>> get_resource_path("assets/icon.svg")
        Path('/path/to/app/assets/icon.svg')
    """
    return get_base_path() / relative_path


def get_resource_str(relative_path: str) -> str:
    """
    Get absolute path to a resource file as string.
    
    Args:
        relative_path: Path relative to the application's base directory
        
    Returns:
        Absolute path string to the resource
    """
    return str(get_resource_path(relative_path))

