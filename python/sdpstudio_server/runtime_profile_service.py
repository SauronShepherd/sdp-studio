"""Validation rules shared by runtime-profile persistence boundaries."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class KubernetesRuntimeConfig(BaseModel):
    """Typed, provider-neutral Kubernetes submission profile contract."""

    model_config = ConfigDict(extra="allow")
    master: str | None = None
    image: str | None = None
    storage_uri: str | None = None
    kube_context: str | None = None
    api_endpoint: str | None = None
    namespace: str = "default"
    service_account: str | None = None
    driver_cores: int | None = Field(default=None, ge=1)
    executor_cores: int | None = Field(default=None, ge=1)
    executor_instances: int | None = Field(default=None, ge=1)

    @field_validator("master", "image", "storage_uri")
    @classmethod
    def single_line(cls, value: str | None) -> str | None:
        if value is not None and (not value.strip() or any(char in value for char in "\r\n\x00")):
            raise ValueError("Kubernetes profile values must be non-empty single-line strings")
        return value


def validate_runtime_profile(adapter: str, config: dict[str, Any]) -> None:
    """Validate an adapter name and reject credentials embedded in config."""
    builtin_adapters = {"local", "spark-connect", "kubernetes", "databricks-connect", "databricks"}
    if adapter not in builtin_adapters:
        from sdpstudio_runners.adapters import discover_runtime_plugins

        if adapter not in discover_runtime_plugins():
            raise ValueError(f"Unsupported runtime adapter: {adapter}")
    environment = config.get("environment")
    if environment is not None and (
        not isinstance(environment, dict)
        or any(
            not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", str(key))
            or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", str(value))
            for key, value in environment.items()
        )
    ):
        raise ValueError("Runtime environment mappings must contain valid variable names")
    encoded = json.dumps(config)
    lowered = encoded.lower()
    if (
        any(marker in lowered for marker in ('"token"', '"password"', '"secret"'))
        and "secret://" not in lowered
        and "_env" not in lowered
    ):
        raise ValueError(
            "Runtime profile appears to contain a secret literal; use an *_env setting or secret reference"
        )
    if "token=" in lowered or "password=" in lowered or "secret=" in lowered:
        raise ValueError(
            "Do not embed credentials in runtime connection strings; store the connection string in an environment variable and use remote_env"
        )
    if adapter == "databricks":
        workspace_url = str(config.get("workspace_url") or "")
        if not re.fullmatch(r"https?://[^\s/]+(?:/[^\s]*)?", workspace_url.rstrip("/")):
            raise ValueError("Databricks profile requires an explicit http(s) workspace_url")
        pipeline_id = config.get("pipeline_id")
        if pipeline_id is not None and (
            not isinstance(pipeline_id, str) or not pipeline_id.strip()
        ):
            raise ValueError("Databricks pipeline_id must be a non-empty string")
    if adapter == "kubernetes":
        KubernetesRuntimeConfig.model_validate(config)
        namespace = str(config.get("namespace", "default"))
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,61}[a-z0-9])?", namespace):
            raise ValueError("Kubernetes namespace must be a valid DNS label")
        allowed_namespace_config = config.get("allowed_namespaces")
        allowed_namespaces = (
            [item for item in allowed_namespace_config if isinstance(item, str)]
            if isinstance(allowed_namespace_config, list)
            else None
        )
        if allowed_namespace_config is not None and (
            allowed_namespaces is None or namespace not in allowed_namespaces
        ):
            raise ValueError(
                "Kubernetes namespace is not in the configured administrator allowlist"
            )
        pod_prefix = str(config.get("pod_name_prefix", "sdpstudio-"))
        allowed_prefixes = config.get("allowed_pod_prefixes")
        prefixes = (
            [item for item in allowed_prefixes if isinstance(item, str)]
            if isinstance(allowed_prefixes, list)
            else None
        )
        if allowed_prefixes is not None and (
            prefixes is None or not any(pod_prefix.startswith(item) for item in prefixes)
        ):
            raise ValueError(
                "Kubernetes pod name prefix is not in the configured administrator allowlist"
            )
        service_account = str(config.get("service_account", ""))
        if service_account and not re.fullmatch(
            r"[a-z0-9](?:[a-z0-9.-]{0,61}[a-z0-9])?", service_account
        ):
            raise ValueError("Kubernetes service account must be a valid DNS label")
        allowed_accounts = config.get("allowed_service_accounts")
        if allowed_accounts is not None and (
            not isinstance(allowed_accounts, list)
            or not all(isinstance(item, str) for item in allowed_accounts)
            or service_account not in allowed_accounts
        ):
            raise ValueError(
                "Kubernetes service account is not in the configured administrator allowlist"
            )
        pod_template = config.get("pod_template_path")
        if pod_template is not None:
            value = str(pod_template).replace("\\", "/")
            if (
                not value
                or value.startswith("/")
                or re.match(r"^[A-Za-z]:", value)
                or ".." in value.split("/")
            ):
                raise ValueError("Kubernetes pod template path must be a relative project path")
        references = config.get("secret_references")
        allowed_references = config.get("allowed_secret_references")
        if references is not None and (
            not isinstance(references, list)
            or not all(
                isinstance(item, str) and item.startswith("secret://") for item in references
            )
        ):
            raise ValueError("Kubernetes secret references must use the secret:// form")
        if allowed_references is not None and (
            not isinstance(allowed_references, list)
            or not all(isinstance(item, str) for item in allowed_references)
            or any(item not in allowed_references for item in (references or []))
        ):
            raise ValueError(
                "Kubernetes secret reference is not in the configured administrator allowlist"
            )
