"""Application name, version, and public project links."""

import tomllib

from utilities.resource_path import get_resource_path

REPO_URL = "https://github.com/com55/ABVME"
RELEASES_URL = "https://github.com/com55/ABVME/releases/latest"
AUTHOR_GITHUB_URL = "https://github.com/com55"
AUTHOR_NAME = "com55"


def _project() -> dict:
    path = get_resource_path("pyproject.toml")
    return tomllib.loads(path.read_text(encoding="utf-8"))["project"]


_PROJECT = _project()
APP_NAME = str(_PROJECT["name"])
APP_DESCRIPTION = str(_PROJECT["description"])


def app_version() -> str:
    version_file = get_resource_path("VERSION")
    if version_file.is_file():
        text = version_file.read_text(encoding="utf-8-sig").strip()
        if text:
            return text
    return str(_PROJECT["version"])

def window_title() -> str:
    return f"{APP_NAME} v{app_version()}"


def license_text() -> str:
    path = get_resource_path("LICENSE")
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return "MIT License"
