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
        [
            "git",
            "-C",
            str(path),
            "-c",
            f"core.hooksPath={disabled_hooks}",
            "-c",
            "user.name=SDP Studio User",
            "-c",
            "user.email=sdpstudio@localhost",
            *args,
        ],
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
        result = _git(path, ["init", "-b", "main"], check=False)
        if result.returncode != 0:
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
    result = _git(
        path, ["show", f"{_validate_ref(ref)}:{_validate_blob_path(relative_path)}"], check=False
    )
    if result.returncode != 0:
        raise FileNotFoundError(relative_path)
    return _bounded_text(result.stdout)


def blob_diff(path: Path, left: str, right: str, relative_path: str) -> str:
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
    staged = _git(path, ["diff", "--cached", "--quiet"], check=False)
    if staged.returncode == 0:
        raise ValueError("No staged changes to commit")
    result = _git(path, ["commit", "-m", message], check=False)
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return {"output": (result.stdout + result.stderr).strip(), **status(path)}


def branches(path: Path) -> dict[str, Any]:
    if not (path / ".git").exists():
        return {"current": None, "branches": []}
    current = _git(path, ["branch", "--show-current"], check=False).stdout.strip()
    names = [
        line.strip().lstrip("* ")
        for line in _git(
            path, ["branch", "--format=%(refname:short)"], check=False
        ).stdout.splitlines()
    ]
    return {"current": current, "branches": [n for n in names if n]}


def log(path: Path, limit: int = 50) -> list[dict[str, str]]:
    if limit < 1 or limit > 500:
        raise ValueError("Git log limit must be between 1 and 500")
    if not (path / ".git").exists():
        return []
    result = _git(path, ["log", f"-{limit}", "--format=%H%x1f%an%x1f%aI%x1f%s"])
    bounded_output = _bounded_text(result.stdout)
    return [
        dict(zip(("commit", "author", "timestamp", "subject"), parts, strict=True))
        for line in bounded_output.splitlines()
        for parts in [line.split("\x1f")]
        if len(parts) == 4
    ]


def switch_branch(path: Path, name: str) -> dict[str, Any]:
    _validate_branch_name(name)
    result = _git(path, ["switch", name], check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return branches(path)


def delete_branch(path: Path, name: str, *, force: bool = False) -> dict[str, Any]:
    _validate_branch_name(name)
    if name == branches(path).get("current"):
        raise ValueError("Cannot delete the current Git branch")
    result = _git(path, ["branch", "-D" if force else "-d", name], check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return branches(path)


def tags(path: Path) -> list[str]:
    if not (path / ".git").exists():
        return []
    result = _git(path, ["tag", "--list", "--sort=version:refname"])
    return [line for line in result.stdout.splitlines() if line]


def create_tag(path: Path, name: str, message: str | None = None) -> list[str]:
    _validate_branch_name(name)
    args = ["tag"]
    if message:
        args.extend(["-a", name, "-m", message])
    else:
        args.append(name)
    result = _git(path, args, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return tags(path)


def stash(path: Path, action: str, message: str | None = None) -> dict[str, Any] | list[str]:
    if action == "list":
        result = _git(path, ["stash", "list"], check=False)
        return [line for line in result.stdout.splitlines() if line]
    if action == "create":
        args = ["stash", "push"]
        if message:
            args.extend(["-m", message])
        result = _git(path, args, check=False)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
        return {"output": (result.stdout + result.stderr).strip(), **status(path)}
    if action == "apply":
        result = _git(path, ["stash", "apply"], check=False)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
        return {"output": (result.stdout + result.stderr).strip(), **status(path)}
    raise ValueError("Unsupported stash action")


def conflicts(path: Path) -> list[str]:
    if not (path / ".git").exists():
        return []
    result = _git(path, ["diff", "--name-only", "--diff-filter=U"], check=False)
    return [line for line in result.stdout.splitlines() if line]


def conflict_versions(path: Path, file_path: str, max_bytes: int = 512 * 1024) -> dict[str, str]:
    if max_bytes < 1 or max_bytes > MAX_GIT_TEXT_BYTES:
        raise ValueError(f"Conflict version limit must be between 1 and {MAX_GIT_TEXT_BYTES}")
    candidate = Path(file_path)
    if candidate.is_absolute() or ".." in candidate.parts or not file_path.strip():
        raise ValueError("Invalid conflicted file path")
    if file_path not in conflicts(path):
        raise ValueError("File is not currently conflicted")
    result: dict[str, str] = {}
    for label, stage in (("ours", "2"), ("theirs", "3")):
        blob = _git(path, ["show", f":{stage}:{file_path}"], check=False)
        if blob.returncode != 0:
            raise RuntimeError(blob.stderr.strip() or "Unable to read conflict stage")
        encoded = blob.stdout.encode("utf-8", errors="replace")
        result[label] = encoded[:max_bytes].decode("utf-8", errors="replace")
    return result


def resolve_conflict(path: Path, file_path: str, strategy: str) -> dict[str, Any]:
    if strategy not in {"ours", "theirs"}:
        raise ValueError("Conflict strategy must be ours or theirs")
    candidate = Path(file_path)
    if candidate.is_absolute() or ".." in candidate.parts or not file_path.strip():
        raise ValueError("Invalid conflicted file path")
    if file_path not in conflicts(path):
        raise ValueError("File is not currently conflicted")
    result = _git(path, ["checkout", f"--{strategy}", "--", file_path], check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return stage(path, [file_path])


def stage(path: Path, paths: list[str] | None = None) -> dict[str, Any]:
    args = ["add", "--"] + (paths or ["."])
    result = _git(path, args, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return status(path)


def unstage(path: Path, paths: list[str] | None = None) -> dict[str, Any]:
    args = ["restore", "--staged", "--"] + (paths or ["."])
    result = _git(path, args, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return status(path)


def create_branch(path: Path, name: str) -> dict[str, Any]:
    _validate_branch_name(name)
    init(path)
    result = _git(path, ["switch", "-c", name], check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return branches(path)


def remotes(path: Path) -> dict[str, str]:
    if not (path / ".git").exists():
        return {}
    result = _git(path, ["remote", "-v"], check=False)
    found: dict[str, str] = {}
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] not in found:
            found[parts[0]] = parts[1]
    return found


def _validate_remote_url(url: str) -> None:
    from urllib.parse import urlparse

    value = url.strip()
    if not value or value.startswith("-") or any(ord(c) < 32 for c in value):
        raise ValueError("Invalid Git remote URL")
    if value.startswith(("http://", "https://", "ssh://", "git://")):
        parsed = urlparse(value)
        if not parsed.hostname:
            raise ValueError("Git remote URL must include a host")
        if parsed.username and value.startswith(("http://", "https://")):
            raise ValueError(
                "Do not embed credentials in Git remote URLs; use SSH or a credential helper"
            )
        if parsed.password:
            raise ValueError(
                "Do not embed credentials in Git remote URLs; use SSH or a credential helper"
            )
        return
    if re.fullmatch(r"[A-Za-z0-9._-]+@[A-Za-z0-9.-]+:[A-Za-z0-9._~/-]+", value):
        return
    raise ValueError(
        "Unsupported Git remote transport; use HTTPS, SSH, or git:// (local/ext helper URLs are blocked)"
    )


def clone(remote_url: str, target: Path, branch: str | None = None) -> dict[str, Any]:
    _validate_remote_url(remote_url)
    if branch:
        _validate_branch_name(branch)
    if target.exists():
        raise ValueError("Clone target already exists")
    args = ["git", "clone"]
    if branch:
        args.extend(["--branch", branch])
    args.extend(["--", remote_url, str(target)])
    result = subprocess.run(
        args, check=False, capture_output=True, text=True, shell=False, timeout=180
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    _git(
        target,
        ["config", "--local", "core.hooksPath", str(target / ".sdpstudio" / "disabled-hooks")],
    )
    return status(target)


def set_remote(path: Path, name: str, url: str) -> dict[str, str]:
    _validate_remote_name(name)
    _validate_remote_url(url)
    init(path)
    current = remotes(path)
    if name in current:
        result = _git(path, ["remote", "set-url", name, url], check=False)
    else:
        result = _git(path, ["remote", "add", name, url], check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return remotes(path)


def fetch(path: Path, remote: str = "origin") -> dict[str, Any]:
    _validate_remote_name(remote)
    result = _git(path, ["fetch", "--prune", remote], check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return {"output": (result.stdout + result.stderr).strip(), **status(path)}


def pull(path: Path, remote: str = "origin", branch: str | None = None) -> dict[str, Any]:
    _validate_remote_name(remote)
    args = ["pull", "--ff-only", remote]
    if branch:
        _validate_branch_name(branch)
        args.append(branch)
    result = _git(path, args, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return {"output": (result.stdout + result.stderr).strip(), **status(path)}


def push(path: Path, remote: str = "origin", branch: str | None = None) -> dict[str, Any]:
    _validate_remote_name(remote)
    branch = branch or branches(path).get("current")
    if not branch:
        raise ValueError("No current branch to push")
    _validate_branch_name(str(branch))
    result = _git(path, ["push", "-u", remote, branch], check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return {"output": (result.stdout + result.stderr).strip(), **status(path)}
