"""Utilities package - Helper classes and widgets"""

from importlib import import_module
from typing import Any

__all__ = [
    "DropAction",
    "DropDecision",
    "classify_drop",
    "LaunchCoalescer",
    "FileDropWidget",
    "get_resource_path",
    "get_resource_str",
]

_EXPORTS = {
    "DropAction": ".drop_classifier",
    "DropDecision": ".drop_classifier",
    "classify_drop": ".drop_classifier",
    "LaunchCoalescer": ".launch_coalescer",
    "FileDropWidget": ".file_drop_widget",
    "get_resource_path": ".resource_path",
    "get_resource_str": ".resource_path",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name, __name__), name)
    globals()[name] = value
    return value
