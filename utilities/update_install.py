"""Detect Setup installs and launch Inno Setup /SILENT updates."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence

logger = logging.getLogger(__name__)

_APP_FOLDER_NAME = "ABVME"
_SETUP_PROCESS_NAME = "ABVME-Windows-x64-Setup"


def install_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return (base / _APP_FOLDER_NAME).resolve()


def update_cache_dir() -> Path:
    d = install_dir() / "update"
    d.mkdir(parents=True, exist_ok=True)
    return d


def is_running_as_exe() -> bool:
    import __main__

    return hasattr(__main__, "__compiled__") or bool(getattr(sys, "frozen", False))


def get_running_executable_path() -> Path:
    if sys.argv and sys.argv[0]:
        try:
            argv0 = Path(os.path.abspath(sys.argv[0]))
            if argv0.exists() and argv0.is_file():
                return argv0.resolve()
        except OSError:
            pass
    return Path(sys.executable).resolve()


def is_installed_build() -> bool:
    if not is_running_as_exe():
        return False
    try:
        exe = get_running_executable_path().resolve()
        target = install_dir()
        return exe.parent == target or target in exe.parents
    except OSError:
        return False


def inno_silent_args(log_path: Path) -> list[str]:
    return [
        "/SILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/CLOSEAPPLICATIONS",
        "/FORCECLOSEAPPLICATIONS",
        "/NORESTARTAPPLICATIONS",
        f"/LOG={log_path}",
    ]


def strip_motw(path: Path) -> None:
    if os.name != "nt":
        return
    zone = Path(f"{path}:Zone.Identifier")
    try:
        zone.unlink(missing_ok=True)
    except OSError:
        pass


def _ps_single_quoted(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def build_relaunch_watcher_ps1(pending_json: Path, setup_process_name: str) -> str:
    """Wait for Setup to finish, then relaunch the installed exe.

    Must be started via ShellExecute (not a child of ABVME) so it survives when
    the app hard-exits for a clean install.
    """
    pending_literal = _ps_single_quoted(str(pending_json))
    process_literal = _ps_single_quoted(setup_process_name)
    lines = [
        "$ErrorActionPreference = 'Stop'",
        f"$Meta = Get-Content -LiteralPath {pending_literal} -Raw | ConvertFrom-Json",
        f"$SetupName = {process_literal}",
        "for ($i = 0; $i -lt 120; $i++) {",
        "    if (Get-Process -Name $SetupName -ErrorAction SilentlyContinue) { break }",
        "    Start-Sleep -Milliseconds 500",
        "}",
        "Wait-Process -Name $SetupName -ErrorAction SilentlyContinue",
        # Give Inno a moment to finish copying / releasing ABVME.exe.
        "Start-Sleep -Seconds 1",
        "for ($i = 0; $i -lt 30; $i++) {",
        "    if (Test-Path -LiteralPath $Meta.target_exe_path) { break }",
        "    Start-Sleep -Milliseconds 500",
        "}",
        "if ($Meta.relaunch_args -and @($Meta.relaunch_args).Count -gt 0) {",
        "    Start-Process -FilePath $Meta.target_exe_path -ArgumentList @($Meta.relaunch_args)",
        "} else {",
        "    Start-Process -FilePath $Meta.target_exe_path",
        "}",
        "Remove-Item -LiteralPath $MyInvocation.MyCommand.Path -Force -ErrorAction SilentlyContinue",
    ]
    return "\r\n".join(lines) + "\r\n"


def _shell_execute(file: str, params: str, work_dir: str, *, show_cmd: int = 1) -> None:
    """Launch an independent process via ShellExecuteW (survives ABVME exit)."""
    if os.name != "nt":
        subprocess.Popen(
            [file, *params.split()],
            cwd=work_dir or None,
            close_fds=True,
            start_new_session=True,
        )
        return
    import ctypes

    result = ctypes.windll.shell32.ShellExecuteW(  # type: ignore[attr-defined]
        None,
        "open",
        file,
        params,
        work_dir,
        show_cmd,
    )
    if result <= 32:
        raise OSError(f"ShellExecuteW failed with code {result}")


def launch_setup_and_prepare_relaunch(
    setup_path: Path,
    target_exe: Path,
    relaunch_args: Sequence[str],
) -> None:
    cache = update_cache_dir()
    log_path = cache / f"inno_{int(time.time())}.log"
    pending_json = cache / f"pending_relaunch_{int(time.time() * 1000)}.json"
    watcher_ps1 = cache / f"relaunch_after_{int(time.time() * 1000)}.ps1"

    pending_json.write_text(
        json.dumps(
            {
                "target_exe_path": str(target_exe),
                "relaunch_args": [str(a) for a in relaunch_args],
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )
    watcher_ps1.write_text(
        build_relaunch_watcher_ps1(pending_json, _SETUP_PROCESS_NAME),
        encoding="utf-8",
    )

    strip_motw(setup_path)
    args = inno_silent_args(log_path)
    setup_params = subprocess.list2cmdline(args) if os.name == "nt" else " ".join(args)

    # Independent of ABVME's process tree — Popen children can die with the app.
    watcher_params = (
        f'-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass '
        f'-File "{watcher_ps1}"'
    )
    _shell_execute("powershell.exe", watcher_params, str(cache), show_cmd=0)
    _shell_execute(str(setup_path), setup_params, str(setup_path.parent), show_cmd=1)
    logger.info("Launched setup %s with args %s", setup_path, args)
