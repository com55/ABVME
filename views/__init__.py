"""Views package - UI components"""

from importlib import import_module
from typing import Any

__all__ = [
    "AssetTableWidget",
    "PreviewPanelWidget",
    "ABVMEMainWindow",
    "SaveDialog",
]

_EXPORTS = {
    "AssetTableWidget": ".asset_table_widget",
    "PreviewPanelWidget": ".preview_panel_widget",
    "ABVMEMainWindow": ".main_window",
    "SaveDialog": ".save_dialog",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name, __name__), name)
    globals()[name] = value
    return value
