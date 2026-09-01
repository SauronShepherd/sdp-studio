from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def build_manifest(root: Path, artifacts: list[Path]) -> dict[str, object]:
    entries = []
    for artifact in sorted(artifacts, key=lambda item: item.as_posix()):
        path = artifact if artifact.is_absolute() else root / artifact
        if not path.is_file():
            raise FileNotFoundError(path)
        entries.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": digest(path),
                "size": path.stat().st_size,
            }
        )
    return {"schema": 1, "artifacts": entries}


def main() -> int:
    parser = argparse.ArgumentParser(description="Create deterministic SDP Studio release metadata")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path("dist/release-manifest.json"))
    parser.add_argument("artifacts", nargs="+", type=Path)
    args = parser.parse_args()
    manifest = build_manifest(args.root.resolve(), args.artifacts)
    output = args.output if args.output.is_absolute() else args.root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
