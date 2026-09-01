from __future__ import annotations

import base64
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from sdpstudio_core.models import RuntimeCapabilities


@dataclass(frozen=True)
class DatabricksConfig:
    workspace_url: str
    pipeline_id: str | None = None
    source_root: str | None = None

    @classmethod
    def from_mapping(cls, config: dict[str, Any]) -> DatabricksConfig:
        workspace = str(config.get("workspace_url") or "").rstrip("/")
        if not workspace.startswith(("https://", "http://")):
            raise ValueError("Databricks workspace_url must be an explicit http(s) URL")
        return cls(
            workspace,
            str(config["pipeline_id"]) if config.get("pipeline_id") else None,
            config.get("source_root"),
        )


class DatabricksClient(Protocol):
    def probe(self) -> dict[str, Any]: ...
    def upload_source(self, source_root: Path) -> dict[str, Any]: ...
    def upsert_pipeline(self, definition: dict[str, Any]) -> dict[str, Any]: ...
    def validate(self, pipeline_id: str) -> dict[str, Any]: ...
    def start(
        self, pipeline_id: str, *, full_refresh: bool = False, selected: list[str] | None = None
    ) -> dict[str, Any]: ...
    def get_update(self, update_id: str) -> dict[str, Any]: ...
    def cancel(self, update_id: str) -> dict[str, Any]: ...
    def events(self, update_id: str, *, page_token: str | None = None) -> dict[str, Any]: ...


class DatabricksRestClient:
    """Small dependency-free client for the optional Databricks lifecycle.

    Authentication is read from ``SDPSTUDIO_DATABRICKS_TOKEN`` (falling back
    to the conventional ``DATABRICKS_TOKEN``) and is sent only as an HTTP
    bearer header. The request function is injectable so contract tests never
    make network calls.
    """

    def __init__(
        self,
        config: DatabricksConfig,
        token: str | None = None,
        request: Callable[[str, str, dict[str, Any] | None], dict[str, Any]] | None = None,
    ) -> None:
        self.config = config
        self._token = (
            token
            or os.environ.get("SDPSTUDIO_DATABRICKS_TOKEN")
            or os.environ.get("DATABRICKS_TOKEN")
        )
        self._request_fn = request or self._request_json

    def _request_json(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if not self._token:
            raise ValueError("Databricks authentication token is not configured")
        body = None
        headers = {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}
        if payload is not None:
            body = json.dumps(payload, sort_keys=True).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"{self.config.workspace_url}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
                value = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RuntimeError("Databricks API request failed") from exc
        if not isinstance(value, dict):
            raise RuntimeError("Databricks API returned an invalid JSON object")
        return value

    def probe(self) -> dict[str, Any]:
        try:
            result = self._request_fn("GET", "/api/2.0/pipelines", None)
        except (RuntimeError, ValueError):
            return {"available": False, "sdp": False}
        return {
            "available": True,
            "sdp": True,
            "details": {"pipeline_count": len(result.get("statuses", []))},
        }

    def upload_source(self, source_root: Path) -> dict[str, Any]:
        root = source_root.resolve()
        if not root.is_dir():
            raise ValueError("Databricks source_root must be a directory")

        def allowed(path: Path) -> bool:
            relative_parts = path.relative_to(root).parts
            if any(
                part in {".git", ".sdpstudio", "__pycache__", "node_modules"}
                for part in relative_parts
            ):
                return False
            name = path.name.lower()
            if name in {".env", ".env.local", ".env.production", ".env.development"}:
                return False
            return not any(
                marker in name for marker in ("secret", "password", "token", "credential")
            )

        files = [path for path in sorted(root.rglob("*")) if path.is_file() and allowed(path)]
        digest = hashlib.sha256()
        remote_root = self.config.source_root or f"/Workspace/Shared/sdpstudio/{root.name}"
        uploaded: list[str] = []
        for path in files:
            relative = path.relative_to(root).as_posix()
            content = path.read_bytes()
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(content)
            self._request_fn(
                "POST",
                "/api/2.0/workspace/import",
                {
                    "path": f"{remote_root.rstrip('/')}/{relative}",
                    "format": "AUTO",
                    "overwrite": True,
                    "content": base64.b64encode(content).decode("ascii"),
                },
            )
            uploaded.append(relative)
        return {"path": remote_root, "digest": digest.hexdigest(), "files": uploaded}

    def upsert_pipeline(self, definition: dict[str, Any]) -> dict[str, Any]:
        pipeline_id = definition.get("id") or self.config.pipeline_id
        if pipeline_id:
            return self._request_fn("PUT", f"/api/2.0/pipelines/{pipeline_id}", definition)
        return self._request_fn("POST", "/api/2.0/pipelines", definition)

    def validate(self, pipeline_id: str) -> dict[str, Any]:
        result = self._request_fn("GET", f"/api/2.0/pipelines/{pipeline_id}", None)
        return {"pipeline_id": pipeline_id, "valid": True, "pipeline": result}

    def start(
        self, pipeline_id: str, *, full_refresh: bool = False, selected: list[str] | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"full_refresh": full_refresh}
        if selected:
            payload["refresh_selection"] = selected
        return self._request_fn("POST", f"/api/2.0/pipelines/{pipeline_id}/updates", payload)

    def get_update(self, update_id: str) -> dict[str, Any]:
        return self._request_fn("GET", f"/api/2.0/pipelines/updates/{update_id}", None)

    def cancel(self, update_id: str) -> dict[str, Any]:
        return self._request_fn("POST", f"/api/2.0/pipelines/updates/{update_id}/cancel", {})

    def events(self, update_id: str, *, page_token: str | None = None) -> dict[str, Any]:
        path = f"/api/2.0/pipelines/updates/{update_id}/events"
        if page_token:
            path += f"?page_token={urllib.parse.quote(page_token, safe='')}"
        return self._request_fn("GET", path, None)


class DatabricksAdapter:
    """Provider lifecycle mapper; SDK/authentication stays outside this package."""

    name = "databricks"

    def __init__(self, config: DatabricksConfig, client: DatabricksClient):
        self.config = config
        self.client = client

    def probe(self) -> RuntimeCapabilities:
        result = self.client.probe()
        return RuntimeCapabilities(
            adapter=self.name,
            available=bool(result.get("available", False)),
            spark_version=result.get("spark_version"),
            sdp=bool(result.get("sdp", True)),
            append_flow=bool(result.get("append_flow", True)),
            sink=bool(result.get("sink", True)),
            selective_refresh=bool(result.get("selective_refresh", True)),
            full_refresh=bool(result.get("full_refresh", True)),
            databricks=True,
            details={
                "workspace_url": self.config.workspace_url,
                "pipeline_id_configured": bool(self.config.pipeline_id),
            },
        )

    def synchronize(self, source_root: Path, definition: dict[str, Any]) -> dict[str, Any]:
        upload = self.client.upload_source(source_root)
        pipeline = self.client.upsert_pipeline({**definition, "source": upload})
        return {"upload": upload, "pipeline": pipeline}

    def validate(self, pipeline_id: str | None = None) -> dict[str, Any]:
        return self.client.validate(pipeline_id or self._pipeline_id())

    def start(
        self, *, full_refresh: bool = False, selected: list[str] | None = None
    ) -> dict[str, Any]:
        return self.client.start(
            self._pipeline_id(), full_refresh=full_refresh, selected=selected or []
        )

    def status(self, update_id: str) -> dict[str, Any]:
        return self.client.get_update(update_id)

    def cancel(self, update_id: str) -> dict[str, Any]:
        return self.client.cancel(update_id)

    def events(self, update_id: str, *, page_token: str | None = None) -> dict[str, Any]:
        return self.client.events(update_id, page_token=page_token)

    def _pipeline_id(self) -> str:
        if not self.config.pipeline_id:
            raise ValueError("Databricks pipeline_id is required for lifecycle operations")
        return self.config.pipeline_id
