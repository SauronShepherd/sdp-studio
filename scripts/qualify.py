"""Run the reproducible release-qualification gates and emit a JSON report."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic


def run_gate(root: Path, name: str, command: list[str]) -> dict[str, object]:
    print(json.dumps({"event": "gate_started", "gate": name}, sort_keys=True), flush=True)
    started = monotonic()
    executable = command[0]
    located = shutil.which(executable)
    if located:
        executable = located
    elif sys.platform == "win32":
        executable = (
            shutil.which(f"{executable}.cmd") or shutil.which(f"{executable}.exe") or executable
        )
    resolved = [executable, *command[1:]]
    try:
        result = subprocess.run(resolved, cwd=root, capture_output=True, text=True, timeout=900)
    except FileNotFoundError as exc:
        return {
            "name": name,
            "command": command,
            "passed": False,
            "returncode": 127,
            "stdout_tail": "",
            "stderr_tail": str(exc),
            "duration_seconds": monotonic() - started,
        }
    result_record = {
        "name": name,
        "command": resolved,
        "passed": result.returncode == 0,
        "returncode": result.returncode,
        "stdout_tail": result.stdout[-2000:],
        "stderr_tail": result.stderr[-2000:],
        "duration_seconds": monotonic() - started,
    }
    print(
        json.dumps(
            {
                "event": "gate_finished",
                "gate": name,
                "passed": result_record["passed"],
                "returncode": result_record["returncode"],
                "duration_seconds": result_record["duration_seconds"],
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return result_record


def qualify(
    root: Path,
    *,
    browser: bool = False,
    spark: bool = False,
    kubernetes: bool = False,
    databricks: bool = False,
    release: bool = False,
) -> dict[str, object]:
    # Release candidates must not silently skip environment-backed acceptance
    # gates.  The individual flags remain useful for fast developer feedback.
    if release:
        browser = True
        spark = True
        kubernetes = True
        databricks = True
    py = [sys.executable]
    spark_python = [os.environ.get("SDPSTUDIO_SPARK_PYTHON", sys.executable)]
    gates: list[tuple[str, list[str]]] = [
        ("python-tests", py + ["-m", "pytest", "-q"]),
        (
            "python-format",
            [
                "ruff",
                "format",
                "--check",
                "--exclude",
                "tests/golden",
                "python",
                "tests",
                "scripts",
            ],
        ),
        ("python-lint", ["ruff", "check", "python", "tests", "scripts"]),
        ("python-typecheck", py + ["-m", "mypy"]),
        (
            "codegen-goldens",
            py + ["-m", "pytest", "-q", "tests/test_golden_codegen.py"],
        ),
        (
            "cli-contract",
            py + ["-m", "pytest", "-q", "tests/test_cli_contract.py"],
        ),
        (
            "roundtrip-contract",
            py + ["-m", "pytest", "-q", "tests/test_reconcile.py"],
        ),
        (
            "kubernetes-contract",
            py + ["-m", "pytest", "-q", "tests/test_runtime_profiles.py", "tests/test_adapters.py"],
        ),
        (
            "security-contract",
            py
            + [
                "-m",
                "pytest",
                "-q",
                "tests/test_bind_security.py",
                "tests/test_secrets.py",
                "tests/test_oidc.py",
            ],
        ),
        (
            "databricks-adapter-contract",
            py + ["-m", "pytest", "-q", "tests/test_databricks_adapter.py"],
        ),
        (
            "scheduler-contract",
            py + ["-m", "pytest", "-q", "tests/test_scheduler.py"],
        ),
        (
            "collaboration-contract",
            py
            + [
                "-m",
                "pytest",
                "-q",
                "tests/test_collaboration_capabilities.py",
                "tests/test_collaboration_merge.py",
            ],
        ),
        (
            "git-contract",
            py
            + [
                "-m",
                "pytest",
                "-q",
                "tests/test_git_providers.py",
                "tests/test_git_checkout_route.py",
            ],
        ),
        (
            "contract-tests",
            py
            + [
                "-m",
                "pytest",
                "-q",
                "tests/test_deployment.py",
                "tests/test_architecture_contracts.py",
                "tests/test_core.py",
                "-k",
                "import or yaml or deployment or migration",
            ],
        ),
        ("web-tests", ["pnpm", "--filter", "@sdpstudio/web", "test"]),
        ("web-typecheck", ["pnpm", "--filter", "@sdpstudio/web", "typecheck"]),
        ("web-build", ["pnpm", "--filter", "@sdpstudio/web", "build"]),
        ("package-smoke", py + ["scripts/package_smoke.py"]),
        ("report-audit", py + ["scripts/report_audit.py", "--output", "dist/report-audit.json"]),
        ("license-sbom", [py[0], "scripts/sbom.py", "--output", "dist/sbom.cdx.json"]),
    ]
    gates.append(("license-gate", py + ["scripts/license_gate.py", "dist/sbom.cdx.json"]))
    if release:
        gates.extend(
            [
                ("release-artifacts", py + ["scripts/package_smoke.py", "--root", "."]),
                ("container-smoke", py + ["scripts/container_smoke.py"]),
                (
                    "environment-spark-connect",
                    py + ["scripts/environment_gate.py", "spark-connect"],
                ),
                ("environment-databricks", py + ["scripts/environment_gate.py", "databricks"]),
                ("environment-kind", py + ["scripts/environment_gate.py", "kind"]),
            ]
        )
    if browser:
        gates.append(("browser-e2e", ["pnpm", "--filter", "@sdpstudio/web", "test:e2e"]))
    if spark:
        gates.append(("spark-row-trace", spark_python + ["scripts/spark_row_trace_smoke.py"]))
        gates.append(
            (
                "spark-smoke",
                spark_python
                + [
                    "-c",
                    "import sys; sys.path.insert(0, 'python'); exec(open('tests/spark_preview_smoke.py', encoding='utf-8').read(), {'__file__': 'tests/spark_preview_smoke.py', '__name__': '__main__'})",
                ],
            )
        )
        gates.append(
            (
                "spark-4.2-auto-cdc",
                spark_python
                + [
                    "-c",
                    "import sys; sys.path.insert(0, 'python'); exec(open('tests/spark_auto_cdc_smoke.py', encoding='utf-8').read(), {'__file__': 'tests/spark_auto_cdc_smoke.py', '__name__': '__main__'})",
                ],
            )
        )
    if kubernetes:
        gates.append(
            (
                "kubernetes-kind-contract",
                py
                + [
                    "-m",
                    "pytest",
                    "-q",
                    "tests/test_runtime_profiles.py",
                    "tests/test_adapters.py",
                    "tests/test_run_state.py",
                ],
            )
        )
        gates.append(("kubernetes-kind-live-smoke", py + ["scripts/kubernetes_kind_smoke.py"]))
    if databricks and not release:
        gates.append(("environment-databricks", py + ["scripts/environment_gate.py", "databricks"]))
    results = [run_gate(root, name, command) for name, command in gates]
    return {
        "schema": 1,
        "started_at": datetime.now(UTC).isoformat(),
        "passed": all(bool(item["passed"]) for item in results),
        "gates": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path("dist/qualification.json"))
    parser.add_argument("--browser", action="store_true")
    parser.add_argument("--spark", action="store_true")
    parser.add_argument("--kubernetes", action="store_true")
    parser.add_argument("--databricks", action="store_true")
    parser.add_argument(
        "--release",
        action="store_true",
        help="Run the fail-closed release-candidate gate matrix, including environment-backed gates",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    report = qualify(
        root,
        browser=args.browser,
        spark=args.spark,
        kubernetes=args.kubernetes,
        databricks=args.databricks,
        release=args.release,
    )
    output = args.output if args.output.is_absolute() else root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {"passed": report["passed"], "output": str(output), "gates": len(report["gates"])},
            sort_keys=True,
        )
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
