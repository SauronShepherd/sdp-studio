"""Build and import-test wheel and source-tarball release artifacts."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path


def run(root: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="sdpstudio-package-") as directory:
        output = Path(directory) / "dist"
        target = Path(directory) / "site"
        output.mkdir(parents=True, exist_ok=True)
        target.mkdir()
        subprocess.run(
            [
                sys.executable,
                "-m",
                "build",
                "--wheel",
                "--sdist",
                "--no-isolation",
                "--outdir",
                str(output),
            ],
            cwd=root,
            check=True,
        )
        wheels = sorted(output.glob("*.whl"))
        if len(wheels) != 1:
            raise RuntimeError(f"Expected exactly one wheel, found {len(wheels)}")
        sdists = sorted(output.glob("*.tar.gz"))
        if len(sdists) != 1:
            raise RuntimeError(f"Expected exactly one source archive, found {len(sdists)}")
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--no-deps",
                "--target",
                str(target),
                str(wheels[0]),
            ],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        smoke = (
            "import sys; sys.path.insert(0, r'"
            + str(target)
            + "'); import sdpstudio_core, sdpstudio_cli; "
            "from sdpstudio_cli.main import build_parser; "
            "assert build_parser().prog == 'sdpstudio'"
        )
        subprocess.run([sys.executable, "-c", smoke], cwd=root, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    run(args.root.resolve())
    print("package smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
