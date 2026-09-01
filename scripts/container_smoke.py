"""Validate the release Compose configuration with non-secret smoke values."""

from __future__ import annotations

import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path


def run(root: Path) -> None:
    environment = os.environ.copy()
    environment.setdefault("POSTGRES_PASSWORD", "qualification-only")
    environment.setdefault("SDPSTUDIO_AUTH_TOKEN", "qualification-only")
    subprocess.run(
        ["docker", "compose", "config", "--quiet"], cwd=root, env=environment, check=True
    )
    if not (root / "deploy" / "docker" / "Dockerfile").is_file():
        return
    image = "sdpstudio-server:qualification"
    container = "sdpstudio-container-smoke"
    subprocess.run(
        [
            "docker",
            "build",
            "--target",
            "server",
            "-t",
            image,
            "-f",
            "deploy/docker/Dockerfile",
            ".",
        ],
        cwd=root,
        check=True,
    )
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-d",
            "--name",
            container,
            "-e",
            "SDPSTUDIO_AUTH_TOKEN=qualification-only",
            "-p",
            "127.0.0.1:18787:8787",
            image,
        ],
        cwd=root,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen("http://127.0.0.1:18787/health", timeout=2) as response:
                    if response.status == 200:
                        return
            except (OSError, urllib.error.URLError):
                time.sleep(1)
        raise RuntimeError("Container healthcheck did not become ready")
    finally:
        subprocess.run(["docker", "rm", "-f", container], check=False, capture_output=True)


if __name__ == "__main__":
    run(Path.cwd().resolve())
