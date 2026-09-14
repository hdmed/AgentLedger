from __future__ import annotations

import os
import shutil
import sys

APP_NAME = "OpenCost"


def basename_crossplatform(path: str | None) -> str:
    """Dernier segment d'un chemin Windows ou posix, sur n'importe quel OS.

    `os.path.basename` seul échoue sur les chemins Windows (`C:\\...`)
    quand les tests tournent sous Linux (CI) et inversement.
    """
    import re

    text = str(path or "").strip()
    parts = [p for p in re.split(r"[\\/]+", text) if p]
    return parts[-1] if parts else text


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def app_root() -> str:
    if is_frozen():
        return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.dirname(os.path.abspath(__file__))


def user_root() -> str:
    override = os.environ.get("OPENCOST_USER_DIR") or os.environ.get("OPENCOST_APPDATA")
    if override:
        return os.path.abspath(os.path.expanduser(override))
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, APP_NAME)


def resource_path(*parts: str) -> str:
    return os.path.join(app_root(), *parts)


def user_path(*parts: str) -> str:
    return os.path.join(user_root(), *parts)


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def data_path(name: str) -> str:
    if is_frozen() or os.environ.get("OPENCOST_USER_DIR") or os.environ.get("OPENCOST_APPDATA"):
        path = os.path.join(user_root(), "data", name)
        ensure_dir(os.path.dirname(path))
        return path
    return resource_path("data", name)


def state_path() -> str:
    return data_path("sync_state.json")


def dataset_path() -> str:
    return data_path("dataset.json")


def report_path() -> str:
    if is_frozen() or os.environ.get("OPENCOST_USER_DIR") or os.environ.get("OPENCOST_APPDATA"):
        path = os.path.join(user_root(), "dist", "report.html")
        ensure_dir(os.path.dirname(path))
        return path
    return resource_path("dist", "report.html")


def config_path(name: str) -> str:
    if is_frozen() or os.environ.get("OPENCOST_USER_DIR") or os.environ.get("OPENCOST_APPDATA"):
        target = os.path.join(user_root(), "config", name)
        ensure_dir(os.path.dirname(target))
        bundled = resource_path("config", name)
        if not os.path.exists(target) and os.path.exists(bundled):
            shutil.copyfile(bundled, target)
        return target
    return resource_path("config", name)


def pricing_path() -> str:
    return config_path("pricing.json")


def budgets_path() -> str:
    return config_path("budgets.json")


def default_db_path() -> str:
    override = os.environ.get("OPENCODE_DB")
    if override:
        return os.path.abspath(os.path.expanduser(override))
    if os.name == "nt":
        return os.path.join(os.environ.get("USERPROFILE") or os.path.expanduser("~"), ".local", "share", "opencode", "opencode.db")
    return os.path.join(os.path.expanduser("~"), ".local", "share", "opencode", "opencode.db")
