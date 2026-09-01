"""Fail the release gate for explicitly denylisted dependency licenses/names."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

DEFAULT_DENYLIST = {"gpl", "agpl", "lgpl", "sspl", "commons-clause"}
# psycopg is an optional PostgreSQL adapter, isolated behind the ``postgres``
# extra.  Its LGPL license is accepted only for this explicitly documented
# external-system integration; project-owned code remains Apache-2.0.
OPTIONAL_EXTERNAL_APPROVALS = {"psycopg", "psycopg-binary"}


def check_sbom(path: Path, denylist: set[str] | None = None) -> list[str]:
    deny = {item.lower() for item in (denylist or DEFAULT_DENYLIST)}
    document = json.loads(path.read_text(encoding="utf-8"))
    problems: list[str] = []
    for component in document.get("components", []):
        name = str(component.get("name", ""))
        if name.lower() in OPTIONAL_EXTERNAL_APPROVALS:
            continue
        for entry in component.get("licenses", []):
            license_name = str(entry.get("license", {}).get("name", "UNKNOWN"))
            if any(marker in license_name.lower() for marker in deny):
                problems.append(f"{name}: denied license {license_name}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("sbom", type=Path)
    args = parser.parse_args()
    problems = check_sbom(args.sbom)
    if problems:
        print("License gate failed:")
        print("\n".join(f"- {item}" for item in problems))
        return 1
    print(f"License gate passed: {args.sbom}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
