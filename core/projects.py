"""Project identity and path helpers."""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from core.storage import load_projects


def normalize_git_remote(url: str) -> str:
    cleaned = url.strip()
    if cleaned.startswith("git@"):
        host_path = cleaned.split(":", 1)
        if len(host_path) == 2:
            host, repo = host_path
            repo = repo.removesuffix(".git")
            return f"{host.replace('git@', '')}/{repo}"
    parsed = urlparse(cleaned)
    if parsed.netloc and parsed.path:
        repo = parsed.path.strip("/").removesuffix(".git")
        return f"{parsed.netloc}/{repo}"
    return cleaned.removesuffix(".git")


def project_id_for_root(workspace_root: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", workspace_root, "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return normalize_git_remote(result.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    digest = hashlib.sha256(workspace_root.encode("utf-8")).hexdigest()[:16]
    return f"local:{digest}"


def project_label(project_id: str, workspace_root: str) -> str:
    projects = load_projects()
    entry = projects.get(project_id)
    if isinstance(entry, dict) and entry.get("label"):
        return str(entry["label"])
    if isinstance(entry, str):
        return entry
    if project_id.startswith("local:"):
        return Path(workspace_root).name
    parts = project_id.split("/")
    return parts[-1] if parts else project_id


def build_project_context(workspace_root: str) -> dict[str, str]:
    project_id = project_id_for_root(workspace_root)
    return {
        "project_id": project_id,
        "project_label": project_label(project_id, workspace_root),
        "workspace_root": workspace_root,
        "workspace_name": Path(workspace_root).name,
    }


def relativize_path(file_path: str, workspace_root: str) -> str:
    root_with_sep = workspace_root if workspace_root.endswith(os.sep) else workspace_root + os.sep
    if file_path == workspace_root:
        return "."
    if file_path.startswith(root_with_sep):
        return os.path.relpath(file_path, workspace_root)
    return file_path
