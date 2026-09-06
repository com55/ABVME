"""Utilities package - Helper classes and widgets"""

# Eager imports so Nuitka (and similar freezers) include these modules.
# Lazy importlib.__getattr__ is invisible to static dependency analysis.
from .drop_classifier import DropAction, DropDecision, classify_drop
from .file_drop_widget import FileDropWidget
from .launch_coalescer import LaunchCoalescer
from .resource_path import get_resource_path, get_resource_str

__all__ = [
    "DropAction",
    "DropDecision",
    "classify_drop",
    "LaunchCoalescer",
    "FileDropWidget",
    "get_resource_path",
    "get_resource_str",
]
