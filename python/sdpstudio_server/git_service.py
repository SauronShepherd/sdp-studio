from __future__ import annotations

import hashlib
import os
import re
import subprocess
from pathlib import Path
from typing import Any

MAX_GIT_TEXT_BYTES = 1_000_000


def _bounded_text(value: str) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) <= MAX_GIT_TEXT_BYTES:
        return value
    marker = b"\n[SDPSTUDIO-GIT-OUTPUT-TRUNCATED]\n"
    return (encoded[: MAX_GIT_TEXT_BYTES - len(marker)] + marker).decode("utf-8", errors="ignore")


def _git(path: Path, args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    disabled_hooks = path / ".sdpstudio" / "disabled-hooks"
    disabled_hooks.parent.mkdir(parents=True, exist_ok=True)
    # Do not leak application credentials or unrelated process configuration
    # into repository operations. Preserve only variables Git uses for binary
    # discovery, locale, and explicitly configured non-secret SSH behavior.
    environment = {
        key: value
        for key, value in os.environ.items()
        if key
        in {
            "PATH",
            "HOME",
            "USERPROFILE",
            "SYSTEMROOT",
            "TEMP",
            "TMP",
            "LANG",
            "LC_ALL",
            "GIT_SSH_COMMAND",
            "GIT_CONFIG_NOSYSTEM",
        }
    }
    environment["GIT_TERMINAL_PROMPT"] = "0"
    return subprocess.run(
        ["git", "-C", str(path), "-c", f"core.hooksPath={disabled_hooks}", *args],
        check=check,
        capture_output=True,
        text=True,
        shell=False,
        timeout=60,
        env=environment,
    )


def _validate_remote_name(name: str) -> None:
    if not name or name.startswith("-") or not all(c.isalnum() or c in "-_." for c in name):
        raise ValueError("Invalid Git remote name")


def _validate_branch_name(name: str) -> None:
    if not name or name.startswith("-") or any(c.isspace() for c in name):
        raise ValueError("Invalid Git branch name")
    if (
        any(token in name for token in ("..", "~", "^", ":", "?", "*", "[", "\\"))
        or name.endswith((".", "/"))
        or "//" in name
    ):
        raise ValueError("Invalid Git branch name")


def status(path: Path) -> dict[str, Any]:
    if not (path / ".git").exists():
        return {"initialized": False, "branch": None, "dirty": False, "entries": []}
    result = _git(path, ["status", "--porcelain=v1", "--branch"])
    lines = result.stdout.splitlines()
    branch = lines[0][3:] if lines and lines[0].startswith("## ") else "unknown"
    entries = lines[1:] if lines and lines[0].startswith("## ") else lines
    return {"initialized": True, "branch": branch, "dirty": bool(entries), "entries": entries}


def run_context(path: Path) -> dict[str, Any]:
    """Return bounded, non-secret Git provenance for a run snapshot."""
    if not (path / ".git").exists():
        return {"git_commit": None, "git_dirty": False, "dirty_patch_hash": None}
    commit_result = _git(path, ["rev-parse", "HEAD"], check=False)
    commit = commit_result.stdout.strip() or None
    patch = diff(path)
    return {
        "git_commit": commit,
        "git_dirty": bool(patch),
        "dirty_patch_hash": hashlib.sha256(patch.encode("utf-8")).hexdigest() if patch else None,
    }


def init(path: Path) -> dict[str, Any]:
    if not (path / ".git").exists():
        # Pin the initial branch at creation time. Renaming an unborn branch via
        # `git branch -M` is version-dependent and can silently leave `master`,
        # which makes subsequent operations that target `main` nondeterministic.
        result = _git(path, ["init", "-b", "main"], check=False)
        if result.returncode != 0:
            # Compatibility path for older Git versions that predate `init -b`.
            _git(path, ["init"])
            symbolic = _git(path, ["symbolic-ref", "HEAD", "refs/heads/main"], check=False)
            if symbolic.returncode != 0:
                raise RuntimeError(symbolic.stderr.strip() or "Unable to initialize main branch")
    _git(path, ["config", "--local", "core.hooksPath", str(path / ".sdpstudio" / "disabled-hooks")])
    return status(path)


def diff(path: Path) -> str:
    if not (path / ".git").exists():
        return ""
    unstaged = _git(path, ["diff", "--no-ext-diff", "--unified=3"], check=False).stdout
    staged = _git(path, ["diff", "--cached", "--no-ext-diff", "--unified=3"], check=False).stdout
    return _bounded_text(staged + unstaged)


def _validate_blob_path(relative_path: str) -> str:
    value = relative_path.replace("\\", "/")
    if not value or value.startswith("/") or value.startswith("../") or "/../" in value:
        raise ValueError("Invalid repository blob path")
    return value


def _validate_ref(ref: str) -> str:
    if (
        not ref
        or ref.startswith("-")
        or ".." in ref
        or not re.fullmatch(r"(?:HEAD(?:~[0-9]+)?|[A-Za-z0-9._/-]+)", ref)
    ):
        raise ValueError("Invalid Git revision")
    return ref


def read_blob(path: Path, ref: str, relative_path: str) -> str:
    """Read a committed file without checking out or mutating the worktree."""
    result = _git(
        path, ["show", f"{_validate_ref(ref)}:{_validate_blob_path(relative_path)}"], check=False
    )
    if result.returncode != 0:
        raise FileNotFoundError(relative_path)
    return _bounded_text(result.stdout)


def blob_diff(path: Path, left: str, right: str, relative_path: str) -> str:
    """Return a committed blob diff without checkout."""
    result = _git(
        path,
        [
            "diff",
            "--no-ext-diff",
            "--unified=3",
            _validate_ref(left),
            _validate_ref(right),
            "--",
            _validate_blob_path(relative_path),
        ],
        check=False,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr.strip() or "Unable to compare Git blobs")
    return _bounded_text(result.stdout)


def commit(path: Path, message: str) -> dict[str, Any]:
    init(path)
    if not message.strip():
        raise ValueError("Commit message must not be empty")
    # Respect explicit staging. This keeps the commit operation from silently
    # adding unrelated files in a shared project workspace.
    staged = _git(path, ["diff", "--cached", "--quiet"], check=False)
    if staged.returncode == 0:
        raise ValueError("No staged changes to commit")
    result = _git(
        path,
        [
            "-c",
            "user.name=SDP Studio User",
            "-c",
            "user.email=sdpstudio@localhost",
            "commit",
            "-m",
            message,
        ],
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Unable to commit changes")
    return status(path)


def stage(path: Path, paths: list[str] | None = None) -> dict[str, Any]:
    init(path)
    values = paths or ["."]
    for value in values:
        if value.startswith("-"):
            raise ValueError("Invalid Git path")
    _git(path, ["add", "--", *values])
    return status(path)


def set_remote(path: Path, name: str, url: str) -> dict[str, Any]:
    init(path)
    _validate_remote_name(name)
    _validate_remote_url(url)
    current = _git(path, ["remote", "get-url", name], check=False)
    if current.returncode == 0:
        _git(path, ["remote", "set-url", name, url])
    else:
        _git(path, ["remote", "add", name, url])
    return status(path)


def _validate_remote_url(url: str) -> None:
    value = url.strip()
    if not value or value.startswith("-"):
        raise ValueError("Invalid Git remote URL")
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*::", value):
        raise ValueError("Git remote helpers are not allowed")
    if re.match(r"^file://", value, re.IGNORECASE) or value.startswith(("/", "./", "../", "~")):
        raise ValueError("Local Git remotes are not allowed")
    if re.match(r"^https?://[^/@]+:[^/@]+@", value, re.IGNORECASE):
        raise ValueError("Embedded credentials are not allowed")
    if re.match(r"^ssh://", value, re.IGNORECASE):
        return
    if re.match(r"^https?://", value, re.IGNORECASE):
        return
    if re.match(r"^[^@\s]+@[^:\s]+:[^\s]+$", value):
        return
    raise ValueError("Unsupported Git remote URL")


def fetch(path: Path, remote: str = "origin") -> dict[str, Any]:
    _validate_remote_name(remote)
    result = _git(path, ["fetch", "--prune", "--", remote], check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Unable to fetch Git remote")
    return status(path)


def pull(path: Path, remote: str, branch: str) -> dict[str, Any]:
    _validate_remote_name(remote)
    _validate_branch_name(branch)
    result = _git(path, ["pull", "--ff-only", "--", remote, branch], check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Unable to pull Git branch")
    return status(path)


def push(path: Path, remote: str = "origin", branch: str | None = None) -> dict[str, Any]:
    _validate_remote_name(remote)
    target = branch or status(path)["branch"]
    _validate_branch_name(str(target))
    result = _git(path, ["push", "--", remote, str(target)], check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Unable to push Git branch")
    return status(path)


def create_branch(path: Path, name: str, start_point: str = "main") -> dict[str, Any]:
    _validate_branch_name(name)
    _validate_ref(start_point)
    result = _git(path, ["switch", "-c", name, start_point], check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Unable to create Git branch")
    return status(path)


def switch_branch(path: Path, name: str) -> dict[str, Any]:
    _validate_branch_name(name)
    result = _git(path, ["switch", name], check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Unable to switch Git branch")
    return status(path)


def delete_branch(path: Path, name: str) -> dict[str, Any]:
    _validate_branch_name(name)
    current = str(status(path)["branch"])
    if current == name:
        raise ValueError("Cannot delete the current Git branch")
    result = _git(path, ["branch", "-D", "--", name], check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Unable to delete Git branch")
    return status(path)


def list_branches(path: Path) -> list[str]:
    if not (path / ".git").exists():
        return []
    result = _git(path, ["for-each-ref", "--format=%(refname:short)", "refs/heads/"])
    return [line for line in result.stdout.splitlines() if line]


def create_tag(path: Path, name: str) -> list[str]:
    _validate_ref(name)
    result = _git(path, ["tag", name], check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Unable to create Git tag")
    return list_tags(path)


def list_tags(path: Path) -> list[str]:
    result = _git(path, ["tag", "--list"])
    return [line for line in result.stdout.splitlines() if line]


def log(path: Path, limit: int = 50) -> list[dict[str, str]]:
    if limit < 1 or limit > 200:
        raise ValueError("Git log limit must be between 1 and 200")
    if not (path / ".git").exists():
        return []
    result = _git(
        path,
        [
            "log",
            f"-{limit}",
            "--date=iso-strict",
            "--pretty=format:%H%x1f%an%x1f%ad%x1f%s",
        ],
    )
    entries = []
    for line in result.stdout.splitlines():
        parts = line.split("\x1f", 3)
        if len(parts) == 4:
            commit_hash, author, timestamp, subject = parts
            entries.append(
                {
                    "hash": commit_hash,
                    "author": _bounded_text(author),
                    "timestamp": timestamp,
                    "subject": _bounded_text(subject),
                }
            )
    return entries


def conflicts(path: Path) -> list[str]:
    result = _git(path, ["diff", "--name-only", "--diff-filter=U"], check=False)
    return [line for line in result.stdout.splitlines() if line]


def conflict_versions(path: Path, relative_path: str, limit: int = 200_000) -> dict[str, str]:
    if limit < 1 or limit > MAX_GIT_TEXT_BYTES:
        raise ValueError("Conflict version limit must be between 1 and MAX_GIT_TEXT_BYTES")
    clean = _validate_blob_path(relative_path)
    values: dict[str, str] = {}
    for stage, label in ((1, "base"), (2, "ours"), (3, "theirs")):
        result = _git(path, ["show", f":{stage}:{clean}"], check=False)
        if result.returncode == 0:
            encoded = result.stdout.encode("utf-8")
            if len(encoded) > limit:
                raise ValueError(f"Conflict {label} version exceeds limit")
            values[label] = result.stdout
    return values


def resolve_conflict(path: Path, relative_path: str, strategy: str) -> dict[str, Any]:
    clean = _validate_blob_path(relative_path)
    if strategy not in {"ours", "theirs"}:
        raise ValueError("Conflict resolution strategy must be 'ours' or 'theirs'")
    result = _git(path, ["checkout", f"--{strategy}", "--", clean], check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Unable to resolve Git conflict")
    _git(path, ["add", "--", clean])
    return status(path)


def checkout(path: Path, ref: str) -> dict[str, Any]:
    _validate_ref(ref)
    result = _git(path, ["checkout", ref], check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Unable to checkout Git revision")
    return status(path)
