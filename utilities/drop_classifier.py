from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

OPEN_SUFFIXES = frozenset({".bundle", ".unity3d"})
TEXTURE_REPLACE_SUFFIXES = frozenset({
    ".png", ".jpg", ".jpeg", ".bmp", ".tga", ".dds",
})
_UNITYFS_MAGIC = b"UnityFS"
_UNITYFS_MIN_LENGTH = 8


class DropAction(StrEnum):
    OPEN = "open"
    REPLACE = "replace"
    REPLACE_CONFIRM = "replace_confirm"
    REJECT = "reject"


@dataclass(frozen=True)
class DropDecision:
    action: DropAction
    file_paths: tuple[str, ...]
    title: str
    detail: str


def suffix_in_container(file_path: str, container: str) -> bool:
    suffix = Path(file_path).suffix.lower()
    if not suffix or not container:
        return False
    container_suffixes = [part.lower() for part in Path(container).suffixes]
    return suffix in container_suffixes


def _has_unityfs_header(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            header = handle.read(_UNITYFS_MIN_LENGTH)
    except OSError:
        return False
    return len(header) >= _UNITYFS_MIN_LENGTH and header[:7] == _UNITYFS_MAGIC


def _is_open_file(path_str: str) -> bool:
    path = Path(path_str)
    if path.suffix.lower() in OPEN_SUFFIXES:
        return True
    return path.is_file() and _has_unityfs_header(path)


def _display_names(files: tuple[str, ...]) -> str:
    names = ", ".join(Path(item).name for item in files[:3])
    extra = len(files) - 3
    if extra > 0:
        names += f" (+{extra})"
    return names


def classify_drop(
    paths: list[str],
    selected_type: str | None,
    selected_name: str | None,
    selected_container: str | None,
    can_replace: bool,
) -> DropDecision:
    files = tuple(path for path in paths if path)
    if not files:
        return DropDecision(DropAction.REJECT, (), "Cannot drop", "No files")

    names = _display_names(files)
    open_flags = tuple(_is_open_file(path) for path in files)

    if all(open_flags):
        return DropDecision(DropAction.OPEN, files, "Open Asset Bundles", names)

    if any(open_flags):
        return DropDecision(
            DropAction.REJECT,
            files,
            "Cannot drop",
            "Do not mix bundle files with replacement files",
        )

    if not can_replace or not selected_type or not selected_name:
        return DropDecision(
            DropAction.REJECT,
            files,
            "Cannot drop",
            "Select one replaceable asset first",
        )

    if selected_type == "Texture2D":
        suffixes = {Path(path).suffix.lower() for path in files}
        if suffixes <= TEXTURE_REPLACE_SUFFIXES:
            return DropDecision(
                DropAction.REPLACE,
                files,
                "Replace",
                f"{names} → {selected_name}",
            )
        return DropDecision(
            DropAction.REJECT,
            files,
            "Cannot drop",
            f"{names} is not an image for Texture2D",
        )

    if selected_type == "TextAsset":
        container = selected_container or ""
        if all(suffix_in_container(path, container) for path in files):
            return DropDecision(
                DropAction.REPLACE,
                files,
                "Replace",
                f"{names} → {selected_name}",
            )
        return DropDecision(
            DropAction.REPLACE_CONFIRM,
            files,
            "Replace (confirm)",
            f"{names} → {selected_name}",
        )

    return DropDecision(
        DropAction.REJECT,
        files,
        "Cannot drop",
        f"Replace is not supported for {selected_type}",
    )
