from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from utilities.drop_classifier import TEXTURE_REPLACE_SUFFIXES, suffix_in_container


class MatchStatus(StrEnum):
    MATCHED = "matched"
    AMBIGUOUS = "ambiguous"
    NO_MATCH = "no_match"


@dataclass(frozen=True)
class ReplaceTarget:
    index: int
    name: str
    kind: str
    container: str
    path_id: str


@dataclass(frozen=True)
class FileMatch:
    file_path: str
    kind: str
    target_index: int | None
    status: MatchStatus


def file_kind(file_path: str) -> str:
    if Path(file_path).suffix.lower() in TEXTURE_REPLACE_SUFFIXES:
        return "Texture2D"
    return "TextAsset"


def _best_by_container(
    file_path: str, candidates: list[ReplaceTarget]
) -> list[ReplaceTarget]:
    file_name = Path(file_path).name.lower()

    def score(target: ReplaceTarget) -> int:
        container = target.container.lower()
        return (2 if file_name in container else 0) + (
            1 if suffix_in_container(file_path, target.container) else 0
        )

    best = max(score(target) for target in candidates)
    return [target for target in candidates if score(target) == best]


def _match_one(file_path: str, targets: list[ReplaceTarget]) -> FileMatch:
    kind = file_kind(file_path)
    path = Path(file_path)
    of_kind = [target for target in targets if target.kind == kind]

    candidates: list[ReplaceTarget] = []
    for name in (path.name.lower(), path.stem.lower()):
        candidates = [target for target in of_kind if target.name.lower() == name]
        if candidates:
            break

    if len(candidates) > 1:
        candidates = _best_by_container(file_path, candidates)

    if not candidates:
        return FileMatch(file_path, kind, None, MatchStatus.NO_MATCH)
    if len(candidates) > 1:
        return FileMatch(file_path, kind, None, MatchStatus.AMBIGUOUS)
    return FileMatch(file_path, kind, candidates[0].index, MatchStatus.MATCHED)


def match_files(
    file_paths: list[str], targets: list[ReplaceTarget]
) -> list[FileMatch]:
    return [_match_one(path, targets) for path in file_paths]
