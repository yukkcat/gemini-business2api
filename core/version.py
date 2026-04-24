from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Dict, Optional, Tuple

import httpx


ROOT_DIR = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT_DIR / "VERSION"
DEFAULT_REPOSITORY = str(
    os.getenv("GEMINI_BUSINESS2API_REPOSITORY")
    or os.getenv("GEMINI_WEB2API_REPOSITORY")
    or "Dreamy-rain/gemini-business2api"
).strip()


def get_app_version() -> str:
    try:
        value = VERSION_FILE.read_text(encoding="utf-8").strip()
        if value:
            return value
    except Exception:
        pass
    env_version = str(os.getenv("GEMINI_BUSINESS2API_VERSION") or "").strip()
    return env_version or "0.0.0"


def get_git_commit_short() -> str:
    env_value = str(
        os.getenv("GEMINI_BUSINESS2API_GIT_SHA")
        or os.getenv("GEMINI_WEB2API_GIT_SHA")
        or ""
    ).strip()
    if env_value:
        return env_value[:12]
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=str(ROOT_DIR),
                stderr=subprocess.DEVNULL,
                text=True,
            )
            .strip()
        )
    except Exception:
        return ""


def get_version_info() -> Dict[str, str]:
    version = get_app_version()
    commit = get_git_commit_short()
    return {
        "version": version,
        "tag": f"v{version}",
        "commit": commit,
    }


def _normalize_tag(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    return raw[1:] if raw.lower().startswith("v") else raw


def _parse_version_key(value: str) -> Tuple[Tuple[int, ...], int, int, int]:
    normalized = _normalize_tag(value)
    if not normalized:
        return tuple(), -1, -1, -1

    match = re.match(
        r"^(?P<release>\d+(?:\.\d+)*)(?:[-._]?(?P<pre>[a-zA-Z]+)(?:[-._]?(?P<pre_num>\d+))?)?$",
        normalized,
    )
    if not match:
        numbers = re.findall(r"\d+", normalized)
        if not numbers:
            return tuple(), -1, -1, -1
        return tuple(int(item) for item in numbers), 1, 99, 0

    release = tuple(int(item) for item in match.group("release").split("."))
    pre_label = str(match.group("pre") or "").lower()
    pre_num = int(match.group("pre_num") or 0)
    if not pre_label:
        return release, 1, 99, 0

    pre_order = {
        "dev": 0,
        "a": 1,
        "alpha": 1,
        "b": 2,
        "beta": 2,
        "rc": 3,
    }
    return release, 0, pre_order.get(pre_label, 0), pre_num


def _fetch_latest_tag(repository: str) -> Tuple[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "gemini-business2api-update-check",
    }

    with httpx.Client(timeout=10.0, follow_redirects=True, headers=headers) as client:
        release_resp = client.get(f"https://api.github.com/repos/{repository}/releases/latest")
        if release_resp.status_code == 200:
            payload = release_resp.json()
            latest_tag = str(payload.get("tag_name") or "").strip()
            html_url = str(payload.get("html_url") or "").strip()
            if latest_tag:
                return latest_tag, html_url

        tags_resp = client.get(f"https://api.github.com/repos/{repository}/tags?per_page=1")
        tags_resp.raise_for_status()
        items = tags_resp.json() if isinstance(tags_resp.json(), list) else []
        if not items:
            raise RuntimeError("no tags found in upstream repository")
        first = items[0] or {}
        return str(first.get("name") or "").strip(), f"https://github.com/{repository}/tags"


def _fetch_latest_tag_from_git_remote() -> Tuple[str, str]:
    try:
        output = subprocess.check_output(
            ["git", "ls-remote", "--tags", "--refs", "origin"],
            cwd=str(ROOT_DIR),
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except Exception as exc:
        raise RuntimeError(f"git remote tag check failed: {exc}") from exc

    tag_names = []
    for raw_line in output.splitlines():
        parts = raw_line.strip().split()
        if len(parts) != 2:
            continue
        ref = parts[1]
        if not ref.startswith("refs/tags/"):
            continue
        tag_names.append(ref.split("refs/tags/", 1)[1].strip())

    if not tag_names:
        raise RuntimeError("no remote tags found")

    latest = max(tag_names, key=_parse_version_key)
    return latest, ""


def get_update_status(repository: Optional[str] = None) -> Dict[str, object]:
    current = get_version_info()
    repo = str(repository or DEFAULT_REPOSITORY or "").strip()
    latest_tag = ""
    latest_version = ""
    release_url = ""
    error = ""

    try:
        latest_tag, release_url = _fetch_latest_tag(repo)
        latest_version = _normalize_tag(latest_tag)
    except Exception as exc:
        error = str(exc)
        try:
            latest_tag, release_url = _fetch_latest_tag_from_git_remote()
            latest_version = _normalize_tag(latest_tag)
            if latest_tag and not release_url and repo:
                release_url = f"https://github.com/{repo}/tags"
            error = ""
        except Exception as git_exc:
            error = f"{error}; {git_exc}"

    current_tuple = _parse_version_key(current["version"])
    latest_tuple = _parse_version_key(latest_version)
    update_available = bool(latest_tuple[0] and current_tuple[0] and latest_tuple > current_tuple)
    is_latest = bool(latest_tuple[0]) and not update_available and latest_tuple == current_tuple

    return {
        **current,
        "repository": repo,
        "latest_tag": latest_tag,
        "latest_version": latest_version,
        "release_url": release_url,
        "is_latest": is_latest,
        "update_available": update_available,
        "check_error": error,
    }
