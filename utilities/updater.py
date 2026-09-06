"""GitHub release update helpers (stdlib urllib — no requests)."""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

WINDOWS_SETUP_ASSET_NAME = "ABVME-Windows-x64-Setup.exe"
WINDOWS_PORTABLE_ASSET_NAME = "ABVME-Windows-x64-Portable.zip"
GITHUB_API_LATEST = "https://api.github.com/repos/com55/ABVME/releases/latest"
GITHUB_RELEASES_PAGE = "https://github.com/com55/ABVME/releases/latest"
_USER_AGENT = "ABVME-updater"


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    browser_download_url: str
    size: int


@dataclass(frozen=True)
class ReleaseInfo:
    latest_version: str
    release_name: str
    release_url: str
    tag_name: str
    body: str
    assets: list[ReleaseAsset]


@dataclass(frozen=True)
class UpdateInfo:
    current_version: str
    latest_version: str
    release_name: str
    release_url: str
    tag_name: str
    body: str
    assets: list[ReleaseAsset]


def version_tuple(v: str) -> tuple[int, ...]:
    match = re.search(r"(\d+(?:\.\d+)*)", v.lstrip("vV"))
    if match:
        return tuple(int(part) for part in match.group(0).split("."))
    return (0,)


def is_newer(latest: str, current: str) -> bool:
    return version_tuple(latest) > version_tuple(current)


def should_check_for_updates(
    last_check: datetime | None,
    *,
    now: datetime,
    interval_days: int = 7,
) -> bool:
    if last_check is None:
        return True
    return now - last_check >= timedelta(days=interval_days)


def find_windows_setup_asset(assets: list[ReleaseAsset]) -> ReleaseAsset:
    for asset in assets:
        if asset.name == WINDOWS_SETUP_ASSET_NAME:
            return asset
    raise FileNotFoundError(
        f"Release asset '{WINDOWS_SETUP_ASSET_NAME}' was not found in latest release"
    )


def format_update_status_message(release_name: str) -> str:
    return (
        f"Update available: {release_name} — open "
        f'<a href="#about">About</a> for details'
    )


def update_info_to_json(info: UpdateInfo) -> str:
    payload = {
        "current_version": info.current_version,
        "latest_version": info.latest_version,
        "release_name": info.release_name,
        "release_url": info.release_url,
        "tag_name": info.tag_name,
        "body": info.body,
        "assets": [
            {
                "name": a.name,
                "browser_download_url": a.browser_download_url,
                "size": a.size,
            }
            for a in info.assets
        ],
    }
    return json.dumps(payload, ensure_ascii=True)


def update_info_from_json(raw: str) -> UpdateInfo | None:
    if not raw or not raw.strip():
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    latest = str(data.get("latest_version") or "").strip()
    if not latest:
        return None
    assets_raw = data.get("assets") or []
    assets: list[ReleaseAsset] = []
    if isinstance(assets_raw, list):
        for item in assets_raw:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            url = str(item.get("browser_download_url") or "").strip()
            try:
                size = int(item.get("size") or 0)
            except (TypeError, ValueError):
                size = 0
            if name and url:
                assets.append(
                    ReleaseAsset(name=name, browser_download_url=url, size=size)
                )
    return UpdateInfo(
        current_version=str(data.get("current_version") or "").strip(),
        latest_version=latest,
        release_name=str(data.get("release_name") or latest).strip(),
        release_url=str(data.get("release_url") or GITHUB_RELEASES_PAGE).strip(),
        tag_name=str(data.get("tag_name") or "").strip(),
        body=str(data.get("body") or ""),
        assets=assets,
    )


def fetch_latest_release(
    opener: Callable[[urllib.request.Request], object] | None = None,
) -> ReleaseInfo:
    request = urllib.request.Request(
        GITHUB_API_LATEST,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": _USER_AGENT,
        },
    )
    open_fn = opener or urllib.request.urlopen
    with open_fn(request) as response:  # type: ignore[operator]
        raw = response.read()
    data = json.loads(raw.decode("utf-8"))

    tag_name = str(data.get("tag_name") or "").strip()
    latest_version = tag_name.lstrip("v") or str(data.get("name") or "").strip()
    release_name = str(data.get("name") or tag_name or latest_version or "Latest Release")
    release_url = str(data.get("html_url") or GITHUB_RELEASES_PAGE)
    body = str(data.get("body") or "")

    assets: list[ReleaseAsset] = []
    for raw_asset in data.get("assets") or []:
        if not isinstance(raw_asset, dict):
            continue
        name = str(raw_asset.get("name") or "").strip()
        url = str(raw_asset.get("browser_download_url") or "").strip()
        try:
            size = int(raw_asset.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        if name and url:
            assets.append(
                ReleaseAsset(name=name, browser_download_url=url, size=size)
            )

    return ReleaseInfo(
        latest_version=latest_version,
        release_name=release_name,
        release_url=release_url,
        tag_name=tag_name,
        body=body,
        assets=assets,
    )


def download_file(
    url: str,
    dest: Path,
    progress_cb: Optional[Callable[[int, Optional[int]], None]] = None,
) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    temp_path = dest.with_suffix(dest.suffix + ".part")
    downloaded = 0
    total: Optional[int] = None

    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            header_total = response.headers.get("Content-Length")
            if header_total:
                try:
                    total = int(header_total)
                except ValueError:
                    total = None
            with temp_path.open("wb") as fh:
                while True:
                    chunk = response.read(1024 * 256)
                    if not chunk:
                        break
                    fh.write(chunk)
                    downloaded += len(chunk)
                    if progress_cb:
                        progress_cb(downloaded, total)
    except Exception:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except OSError:
            pass
        raise

    temp_path.replace(dest)
    if not dest.exists() or dest.stat().st_size <= 0:
        raise OSError("Downloaded file is missing or empty")
    if progress_cb:
        progress_cb(dest.stat().st_size, total)
    return dest


def check_for_updates(current_version: str) -> UpdateInfo | None:
    try:
        latest = fetch_latest_release()
        current = current_version.lstrip("v")
        if is_newer(latest.latest_version, current):
            return UpdateInfo(
                current_version=current,
                latest_version=latest.latest_version,
                release_name=latest.release_name,
                release_url=latest.release_url,
                tag_name=latest.tag_name,
                body=latest.body,
                assets=latest.assets,
            )
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as e:
        logger.warning("Update check failed: %s", e)
    except Exception as e:
        logger.error("Unexpected error during update check: %s", e, exc_info=True)
    return None
