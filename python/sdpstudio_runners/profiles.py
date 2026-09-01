from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import yaml
from sdpstudio_core.models import RuntimeCapabilities

from .local import probe_local


def _spark_pipelines() -> str | None:
    return shutil.which("spark-pipelines")


def _upload_s3_artifact(source: Path, destination: str, expected_sha256: str) -> None:
    """Upload and read back one artifact through the AWS CLI, without shell execution."""
    aws = shutil.which("aws")
    if not aws:
        raise OSError("S3 artifact staging requires the aws CLI")
    subprocess.run([aws, "s3", "cp", str(source), destination, "--only-show-errors"], check=True)
    with tempfile.TemporaryDirectory(prefix="sdpstudio-stage-") as directory:
        downloaded = Path(directory) / source.name
        subprocess.run(
            [aws, "s3", "cp", destination, str(downloaded), "--only-show-errors"], check=True
        )
        actual = hashlib.sha256(downloaded.read_bytes()).hexdigest()
    if actual != expected_sha256:
        raise OSError(f"Staged artifact checksum mismatch: {source.name}")


_SPARK_PIPELINE_FLAGS = frozenset(
    {
        "--spec",
        "--conf",
        "--remote",
        "--master",
        "--deploy-mode",
        "--refresh",
        "--full-refresh",
        "--full-refresh-all",
    }
)


def _probe_spark_pipeline_flags(binary: str) -> frozenset[str] | None:
    """Probe the installed CLI without invoking a shell.

    ``None`` means the binary could not be probed, so compatibility behavior
    remains available for test doubles and older distributions. A returned
    set is authoritative and unsupported requested flags are rejected.
    """
    for arguments in ([binary, "run", "--help"], [binary, "--help"]):
        try:
            result = subprocess.run(
                arguments,
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        output = f"{result.stdout}\n{result.stderr}"
        if result.returncode == 0 and any(flag in output for flag in _SPARK_PIPELINE_FLAGS):
            return frozenset(flag for flag in _SPARK_PIPELINE_FLAGS if flag in output)
    return None


def _resolved_remote(config: dict[str, Any]) -> str | None:
    if config.get("remote"):
        return str(config["remote"])
    env_name = str(config.get("remote_env") or "SPARK_REMOTE")
    return os.environ.get(env_name)


def probe_profile(profile: dict[str, Any]) -> RuntimeCapabilities:
    adapter = profile.get("adapter", "local")
    config = profile.get("config") or {}
    if adapter == "local":
        return probe_local()

    spark_pipelines = _spark_pipelines()
    local = probe_local()
    if adapter == "spark-connect":
        remote = _resolved_remote(config)
        return RuntimeCapabilities(
            adapter=adapter,
            available=bool(spark_pipelines and remote),
            spark_version=local.spark_version,
            sdp=bool(spark_pipelines),
            append_flow=bool(spark_pipelines),
            sink=bool(spark_pipelines),
            selective_refresh=bool(spark_pipelines),
            full_refresh=bool(spark_pipelines),
            spark_connect=True,
            details={
                "spark_pipelines": spark_pipelines,
                "remote_configured": bool(remote),
                "remote_source": "literal"
                if config.get("remote")
                else str(config.get("remote_env") or "SPARK_REMOTE"),
            },
        )
    if adapter == "databricks-connect":
        remote = _resolved_remote(config)
        databricks_connect = (
            importlib.util.find_spec("databricks.connect") is not None
            if importlib.util.find_spec("databricks")
            else False
        )
        return RuntimeCapabilities(
            adapter=adapter,
            available=bool(spark_pipelines and remote),
            spark_version=local.spark_version,
            sdp=bool(spark_pipelines),
            append_flow=bool(spark_pipelines),
            sink=bool(spark_pipelines),
            selective_refresh=bool(spark_pipelines),
            full_refresh=bool(spark_pipelines),
            spark_connect=True,
            details={
                "spark_pipelines": spark_pipelines,
                "remote_configured": bool(remote),
                "remote_source": str(config.get("remote_env") or "SPARK_REMOTE"),
                "databricks_connect_importable": databricks_connect,
                "note": "Databricks is optional; portable pyspark.pipelines code remains the source of truth.",
            },
        )
    if adapter == "kubernetes":
        master = config.get("master")
        image = config.get("image")
        storage_uri = config.get("storage_uri")
        kubectl = shutil.which("kubectl")
        return RuntimeCapabilities(
            adapter=adapter,
            available=bool(
                spark_pipelines
                and master
                and image
                and storage_uri
                and shutil.which("java")
                and kubectl
            ),
            spark_version=local.spark_version,
            sdp=bool(spark_pipelines),
            append_flow=bool(spark_pipelines),
            sink=bool(spark_pipelines),
            selective_refresh=bool(spark_pipelines),
            full_refresh=bool(spark_pipelines),
            kubernetes=True,
            details={
                "spark_pipelines": spark_pipelines,
                "master_configured": bool(master),
                "image_configured": bool(image),
                "storage_uri_configured": bool(storage_uri),
                "kubectl": kubectl,
            },
        )
    return RuntimeCapabilities(
        adapter=str(adapter), available=False, details={"error": "unsupported adapter"}
    )


def probe_kubernetes_live(profile: dict[str, Any]) -> dict[str, Any]:
    """Probe the configured Kubernetes API and namespace without a shell."""
    config = profile.get("config") or {}
    kubectl = str(config.get("kubectl") or shutil.which("kubectl") or "")
    namespace = str(config.get("namespace") or "default")
    if not kubectl:
        return {"ok": False, "code": "SDPS-K8S-PROBE-001", "message": "kubectl is not available"}
    command = [kubectl]
    if config.get("kube_context"):
        command.extend(["--context", str(config["kube_context"])])
    command.extend(["-n", namespace, "get", "namespace", namespace, "-o", "name"])
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, check=False, timeout=20, shell=False
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "code": "SDPS-K8S-PROBE-002", "message": str(exc)}
    if result.returncode != 0:
        return {
            "ok": False,
            "code": "SDPS-K8S-PROBE-003",
            "message": result.stderr.strip() or "Kubernetes namespace probe failed",
        }
    return {"ok": True, "namespace": namespace, "output": result.stdout.strip()}


def _runtime_spec(project: Path, run_id: str, config: dict[str, Any]) -> Path | None:
    storage_uri = config.get("storage_uri")
    if not storage_uri:
        return None
    source = project / "spark-pipeline.yaml"
    data = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    data["storage"] = str(storage_uri)
    if config.get("catalog"):
        data["catalog"] = str(config["catalog"])
    if config.get("database"):
        data["database"] = str(config["database"])
    target = project / ".sdpstudio" / "runtime" / "run-artifacts" / run_id / "spark-pipeline.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    staged_root = target.parent / "staged"
    staged_root.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, str]] = []
    candidates = (
        [source, *sorted((project / "transformations").rglob("*"))]
        if (project / "transformations").is_dir()
        else [source]
    )
    for candidate in candidates:
        if candidate.is_file():
            relative = candidate.relative_to(project)
            staged = staged_root / relative
            staged.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(candidate, staged)
            digest = hashlib.sha256(staged.read_bytes()).hexdigest()
            manifest.append(
                {
                    "path": str(relative).replace("\\", "/"),
                    "staged_path": str(staged.relative_to(project)).replace("\\", "/"),
                    "sha256": digest,
                }
            )
    parsed_storage = urlparse(str(storage_uri))
    if parsed_storage.scheme in {"", "file"}:
        destination_root = (
            Path(unquote(parsed_storage.path if parsed_storage.scheme else str(storage_uri)))
            / run_id
        )
        destination_root.mkdir(parents=True, exist_ok=True)
        for item in manifest:
            source_path = project / item["staged_path"]
            destination_path = destination_root / item["path"]
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_path, destination_path)
            if hashlib.sha256(destination_path.read_bytes()).hexdigest() != item["sha256"]:
                raise OSError(f"Staged artifact checksum mismatch: {item['path']}")
            item["remote_path"] = str(destination_path)
    elif parsed_storage.scheme in {"s3", "s3a", "s3n"}:
        base = (
            str(storage_uri).replace("s3a://", "s3://", 1).replace("s3n://", "s3://", 1).rstrip("/")
        )
        for item in manifest:
            destination = f"{base}/{run_id}/{item['path']}"
            _upload_s3_artifact(project / item["staged_path"], destination, item["sha256"])
            item["remote_path"] = destination
    elif parsed_storage.scheme not in {
        "gs",
        "abfs",
        "abfss",
        "http",
        "https",
    }:
        raise ValueError(f"Unsupported Kubernetes storage URI scheme: {parsed_storage.scheme}")
    manifest_path = target.parent / "staged-artifact-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {"run_id": run_id, "storage_uri": str(storage_uri), "files": manifest},
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    data["sdpstudio_artifact_manifest"] = str(manifest_path.relative_to(project)).replace("\\", "/")
    target.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return target


def _kubernetes_conf(
    config: dict[str, Any], *, driver_name: str | None = None
) -> list[tuple[str, str]]:
    """Build deterministic, explicitly supported Spark-on-Kubernetes settings."""
    image = str(config.get("image") or "")
    if not image or any(char in image for char in "\r\n\x00"):
        raise ValueError("Kubernetes image must be a non-empty single-line value")
    values: list[tuple[str, str]] = [("spark.kubernetes.container.image", image)]
    if driver_name:
        values.append(("spark.kubernetes.driver.pod.name", driver_name))
    fields = {
        "namespace": "spark.kubernetes.namespace",
        "service_account": "spark.kubernetes.authenticate.driver.serviceAccountName",
        "driver_cores": "spark.driver.cores",
        "driver_memory": "spark.driver.memory",
        "executor_cores": "spark.executor.cores",
        "executor_memory": "spark.executor.memory",
        "executor_instances": "spark.executor.instances",
    }
    for source, target in fields.items():
        if config.get(source) is not None:
            value = str(config[source])
            if not value or any(char in value for char in "\r\n\x00"):
                raise ValueError(f"Kubernetes setting {source!r} must be a single-line value")
            values.append((target, value))
    for secret in config.get("image_pull_secrets", []) or []:
        value = str(secret)
        if not value or any(char in value for char in "\r\n\x00"):
            raise ValueError("Kubernetes image pull secret names must be single-line values")
        values.append(("spark.kubernetes.container.image.pullSecrets", value))
    labels = config.get("labels") or {}
    if not isinstance(labels, dict):
        raise ValueError("Kubernetes labels must be a mapping")
    for key in sorted(labels):
        value = str(labels[key])
        if not key or any(char in f"{key}{value}" for char in "\r\n\x00"):
            raise ValueError("Kubernetes labels must be single-line values")
        values.append((f"spark.kubernetes.driver.label.{key}", value))
    annotations = config.get("annotations") or {}
    if not isinstance(annotations, dict):
        raise ValueError("Kubernetes annotations must be a mapping")
    for key in sorted(annotations):
        value = str(annotations[key])
        if not key or any(char in f"{key}{value}" for char in "\r\n\x00"):
            raise ValueError("Kubernetes annotations must be single-line values")
        values.append((f"spark.kubernetes.driver.annotation.{key}", value))
    spark_conf = config.get("spark_conf") or {}
    if not isinstance(spark_conf, dict):
        raise ValueError("spark_conf must be a mapping")
    for key in sorted(spark_conf):
        if not str(key).startswith("spark."):
            raise ValueError("Custom Kubernetes Spark settings must use spark.* keys")
        value = str(spark_conf[key])
        if any(char in value for char in "\r\n\x00"):
            raise ValueError("Spark configuration values must be single-line values")
        values.append((str(key), value))
    return values


def _safe_conf_value(key: str, value: str) -> str:
    lowered = key.lower()
    return (
        "***REDACTED***"
        if any(marker in lowered for marker in ("password", "secret", "token", "credential"))
        else value
    )


def build_run_command(
    profile: dict[str, Any],
    *,
    project: Path,
    run_id: str,
    mode: str,
    selected: list[str],
) -> tuple[list[str], list[str], Path | None]:
    adapter = profile.get("adapter", "local")
    config = profile.get("config") or {}
    binary = _spark_pipelines()
    if not binary:
        raise RuntimeError("spark-pipelines executable is not available")
    supported_flags = _probe_spark_pipeline_flags(binary)

    def require_flag(flag: str) -> None:
        if supported_flags is not None and flag not in supported_flags:
            raise RuntimeError(f"Installed spark-pipelines does not support {flag}")

    temp_spec = (
        _runtime_spec(project, run_id, config)
        if adapter in {"spark-connect", "kubernetes", "databricks-connect"}
        else None
    )
    spec = temp_spec.name if temp_spec else "spark-pipeline.yaml"
    require_flag("--spec")
    command = [binary, "run", "--spec", spec]
    safe = list(command)

    # Keep event logs isolated per run. This is deliberately added as Spark
    # configuration rather than mutating a user's global Spark defaults.
    if adapter == "local":
        require_flag("--conf")
        event_log_dir = (project / ".sdpstudio" / "runtime" / "event-logs" / run_id).resolve()
        event_log_dir.mkdir(parents=True, exist_ok=True)
        event_log_uri = event_log_dir.as_uri()
        command.extend(
            [
                "--conf",
                "spark.eventLog.enabled=true",
                "--conf",
                f"spark.eventLog.dir={event_log_uri}",
            ]
        )
        safe.extend(
            [
                "--conf",
                "spark.eventLog.enabled=true",
                "--conf",
                f"spark.eventLog.dir={event_log_uri}",
            ]
        )

    if adapter in {"spark-connect", "databricks-connect"}:
        remote = _resolved_remote(config)
        if not remote:
            raise RuntimeError("Spark Connect remote is not configured")
        require_flag("--remote")
        command.extend(["--remote", remote])
        safe.extend(["--remote", "***REDACTED_REMOTE***" if "token=" in remote.lower() else remote])
    elif adapter == "kubernetes":
        master = str(config.get("master") or "")
        image = str(config.get("image") or "")
        if not master or not image:
            raise RuntimeError("Kubernetes runtime requires master and image")
        require_flag("--master")
        require_flag("--deploy-mode")
        require_flag("--conf")
        command.extend(["--master", master, "--deploy-mode", "cluster"])
        safe.extend(["--master", master, "--deploy-mode", "cluster"])
        driver_name = str(config.get("driver_name") or f"sdpstudio-{run_id.lower()}-driver")
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", driver_name):
            raise RuntimeError("Kubernetes driver_name must be a valid DNS label")
        conf = _kubernetes_conf(config, driver_name=driver_name)
        for key, value in conf:
            command.extend(["--conf", f"{key}={value}"])
            safe.extend(["--conf", f"{key}={_safe_conf_value(key, value)}"])
    elif adapter != "local":
        raise RuntimeError(f"Unsupported runtime adapter: {adapter}")

    if mode == "full-refresh-all":
        require_flag("--full-refresh-all")
        command.append("--full-refresh-all")
        safe.append("--full-refresh-all")
    elif mode == "full-refresh" and selected:
        require_flag("--full-refresh")
        command.extend(["--full-refresh", ",".join(selected)])
        safe.extend(["--full-refresh", ",".join(selected)])
    elif mode == "refresh" and selected:
        require_flag("--refresh")
        command.extend(["--refresh", ",".join(selected)])
        safe.extend(["--refresh", ",".join(selected)])
    return command, safe, temp_spec
