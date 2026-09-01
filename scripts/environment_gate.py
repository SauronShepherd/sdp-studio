"""Fail-closed checks for environment-backed release qualification targets."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", choices=("spark-connect", "databricks", "kind"))
    args = parser.parse_args(argv)
    if args.target == "spark-connect":
        if not os.environ.get("SDPSTUDIO_RELEASE_SPARK_CONNECT_REMOTE"):
            raise SystemExit("SDPSTUDIO_RELEASE_SPARK_CONNECT_REMOTE is required")
        spark_python = os.environ.get("SDPSTUDIO_SPARK_PYTHON", "python")
        spark_pipelines = shutil.which("spark-pipelines")
        if not spark_pipelines:
            candidate = Path(spark_python).resolve().parent / "Scripts" / "spark-pipelines"
            if candidate.is_file():
                spark_pipelines = str(candidate)
        if not spark_pipelines:
            raise SystemExit("spark-pipelines is required for Spark Connect qualification")
        runtime = subprocess.run(
            [
                spark_python,
                "-c",
                "import pyspark; from pyspark import pipelines; print(pyspark.__version__)",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if runtime.returncode != 0 or not re.match(r"^4\.2(?:\.|$)", runtime.stdout.strip()):
            raise SystemExit(
                "Spark 4.2 with pyspark.pipelines is required for qualification: "
                + (runtime.stderr.strip() or runtime.stdout.strip())
            )
        java = shutil.which("java")
        if not java:
            raise SystemExit("Java 17 or newer is required for Spark 4.2 qualification")
        version = subprocess.run([java, "-version"], check=False, capture_output=True, text=True)
        java_text = version.stdout + version.stderr
        match = re.search(r'version "(\d+)', java_text)
        if version.returncode != 0 or not match or int(match.group(1)) < 17:
            raise SystemExit("Java 17 or newer is required for Spark 4.2 qualification")
    elif args.target == "databricks":
        workspace_url = os.environ.get("SDPSTUDIO_RELEASE_DATABRICKS_WORKSPACE_URL")
        if not workspace_url:
            raise SystemExit("SDPSTUDIO_RELEASE_DATABRICKS_WORKSPACE_URL is required")
        profile = os.environ.get("DATABRICKS_CONFIG_PROFILE")
        if not profile:
            raise SystemExit("DATABRICKS_CONFIG_PROFILE is required")
        databricks = shutil.which("databricks")
        if not databricks:
            raise SystemExit("databricks CLI is required for Databricks qualification")
        describe = subprocess.run(
            [databricks, "auth", "describe", "--profile", profile],
            check=False,
            capture_output=True,
            text=True,
        )
        if describe.returncode != 0:
            raise SystemExit(
                "Databricks authentication failed: "
                + (describe.stderr.strip() or describe.stdout.strip())
            )
        configured_host = next(
            (
                line.split(":", 1)[1].strip()
                for line in describe.stdout.splitlines()
                if line.startswith("Host:")
            ),
            "",
        ).rstrip("/")
        if configured_host != workspace_url.rstrip("/"):
            raise SystemExit(
                f"Databricks profile host {configured_host!r} does not match "
                f"SDPSTUDIO_RELEASE_DATABRICKS_WORKSPACE_URL {workspace_url!r}"
            )
        workspace_probe = subprocess.run(
            [databricks, "clusters", "list", "--profile", profile],
            check=False,
            capture_output=True,
            text=True,
        )
        if workspace_probe.returncode != 0:
            raise SystemExit(
                "Databricks workspace API probe failed: "
                + (workspace_probe.stderr.strip() or workspace_probe.stdout.strip())
            )
    else:
        if not shutil.which("kind") or not shutil.which("kubectl"):
            raise SystemExit("kind and kubectl are required for Kubernetes qualification")
        cluster_name = os.environ.get("SDPSTUDIO_RELEASE_KIND_CLUSTER", "sdpstudio")
        clusters = subprocess.run(
            ["kind", "get", "clusters"], check=True, capture_output=True, text=True
        ).stdout.splitlines()
        if cluster_name not in clusters:
            raise SystemExit(
                f"kind cluster {cluster_name!r} is required for Kubernetes qualification"
            )
        subprocess.run(
            ["kind", "export", "kubeconfig", "--name", cluster_name],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(["kubectl", "cluster-info"], check=True, capture_output=True, text=True)
        nodes = subprocess.run(
            ["kubectl", "get", "nodes", "--no-headers"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        node_rows = [row.split() for row in nodes.splitlines() if row.split()]
        if not node_rows or not any(len(row) > 1 and row[1] == "Ready" for row in node_rows):
            raise SystemExit("Kubernetes qualification cluster has no Ready schedulable nodes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
