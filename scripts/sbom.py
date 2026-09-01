"""Generate a deterministic, dependency-only CycloneDX JSON SBOM.

The generator is intentionally offline: it uses the installed Python metadata and
the repository lockfile, so release jobs do not need a SaaS SBOM service.
"""

from __future__ import annotations

import argparse
import json
import re
import tomllib
from importlib import metadata
from pathlib import Path

import yaml


def _license_from_python_metadata(dist: metadata.Distribution) -> str:
    """Prefer SPDX metadata, then legacy fields and classifiers."""
    package_metadata = dist.metadata
    for field in ("License-Expression", "License"):
        value = package_metadata.get(field)
        if value and str(value).strip().lower() not in {"unknown", "none"}:
            return str(value).strip()
    for classifier in package_metadata.get_all("Classifier", []):
        prefix = "License :: "
        if classifier.startswith(prefix):
            return classifier.removeprefix(prefix).strip()
    return "UNKNOWN"


def _declared_python_names(root: Path) -> set[str]:
    """Return normalized project/dependency names, excluding ambient packages."""
    try:
        document = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return set()
    project = document.get("project") or {}
    requirements = list(project.get("dependencies") or [])
    for values in (project.get("optional-dependencies") or {}).values():
        requirements.extend(values or [])
    names = {str(project.get("name") or "")}
    names.update(re.split(r"[<>=!~;\s\[]", str(item), maxsplit=1)[0] for item in requirements)
    return {re.sub(r"[-_.]+", "-", name).lower() for name in names if name}


def _python_components(root: Path) -> list[dict[str, object]]:
    declared = _declared_python_names(root)
    components = []
    for dist in sorted(
        metadata.distributions(), key=lambda item: item.metadata.get("Name", "").lower()
    ):
        name = dist.metadata.get("Name")
        version = dist.version
        normalized_name = re.sub(r"[-_.]+", "-", str(name or "")).lower()
        if not name or (declared and normalized_name not in declared):
            continue
        license_name = _license_from_python_metadata(dist)
        components.append(
            {
                "type": "library",
                "bom-ref": f"pkg:pypi/{name.lower()}@{version}",
                "name": name,
                "version": version,
                "purl": f"pkg:pypi/{name.lower()}@{version}",
                "licenses": [{"license": {"name": license_name}}],
            }
        )
    return components


def _installed_npm_licenses(root: Path) -> dict[tuple[str, str], str]:
    """Read licenses from installed package manifests without registry access."""
    licenses: dict[tuple[str, str], str] = {}
    package_roots = [root / "node_modules", root / "web" / "node_modules"]
    manifests = [
        manifest
        for package_root in package_roots
        if package_root.exists()
        for manifest in package_root.glob(".pnpm/**/node_modules/**/package.json")
    ]
    for manifest in sorted(set(manifests)):
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            name = str(payload.get("name") or "")
            version = str(payload.get("version") or "")
            license_value = payload.get("license")
            if isinstance(license_value, dict):
                license_value = license_value.get("type")
            if name and version and isinstance(license_value, str) and license_value:
                licenses[(name, version)] = license_value
        except (OSError, ValueError, TypeError):
            continue
    return licenses


def _pnpm_components(lockfile: Path, root: Path) -> list[dict[str, object]]:
    if not lockfile.exists():
        return []
    names: set[str] = set()
    try:
        document = yaml.safe_load(lockfile.read_text(encoding="utf-8")) or {}
        package_entries = document.get("packages", {})
        if isinstance(package_entries, dict):
            for raw_key in package_entries:
                key = str(raw_key).lstrip("/").split("(", 1)[0].strip("'\"")
                if "@" in key:
                    names.add(key)
    except (OSError, TypeError, ValueError, yaml.YAMLError):
        return []
    installed = _installed_npm_licenses(root)
    components = [
        {
            "type": "library",
            "bom-ref": f"pkg:npm/{name}",
            "name": name.rsplit("@", 1)[0] if not name.startswith("@") else name.rsplit("@", 1)[0],
            "version": name.rsplit("@", 1)[-1],
            "purl": f"pkg:npm/{name}",
            "licenses": [
                {
                    "license": {
                        "name": installed.get(
                            (name.rsplit("@", 1)[0], name.rsplit("@", 1)[-1]), "UNKNOWN"
                        )
                    }
                }
            ],
        }
        for name in sorted(names)
    ]
    return components


def build_sbom(root: Path) -> dict[str, object]:
    components = _python_components(root) + _pnpm_components(root / "pnpm-lock.yaml", root)
    components.sort(key=lambda item: (str(item["purl"]), str(item["version"])))
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": "urn:uuid:sdpstudio-deterministic-sbom",
        "version": 1,
        "metadata": {"component": {"type": "application", "name": "sdpstudio", "version": "0.1.0"}},
        "components": components,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path("dist/sbom.cdx.json"))
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(build_sbom(root), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
