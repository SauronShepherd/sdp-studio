from __future__ import annotations

import asyncio
import base64
import binascii
import difflib
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import zipfile
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from pathlib import Path
from time import monotonic
from typing import Any, Literal, cast
from uuid import uuid4

import yaml
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sdpstudio_codegen import discover_python, discover_sql, reconcile_python, reconcile_sql
from sdpstudio_core.capabilities import validate_capabilities
from sdpstudio_core.debug import (
    evaluate_schema_contract,
    execute_row_trace,
    execute_row_trace_spark,
    parse_explain_plan,
    plan_diff,
    profile_diff,
    profile_rows,
    row_trace,
    schema_diff,
    schema_fingerprint,
    semantic_graph_diff,
    static_debug_plan,
    summarize_spark_events,
    summarize_streaming_events,
)
from sdpstudio_core.diagnostics import diagnose
from sdpstudio_core.graph import validate_graph
from sdpstudio_core.models import GenerationResult, PipelineDocument, RuntimeCapabilities
from sdpstudio_core.operators import BUILTIN_OPERATORS
from sdpstudio_core.plugins import PLUGIN_GROUPS, discover_plugins
from sdpstudio_core.quality import evaluate_quality
from sdpstudio_core.quality_suite import (
    QualitySuiteError,
    execute_quality_suite,
    load_quality_suite,
)
from sdpstudio_runners.adapters import DurableLocalRuntimeAdapter, adapter_for
from sdpstudio_runners.local import LocalRuntime, probe_local
from sdpstudio_runners.profiles import probe_kubernetes_live, probe_profile

from . import git_service
from .async_store import AsyncStore
from .auth import AuthService
from .auth_bootstrap import AuthBootstrapService
from .collab import COLLABORATION_CAPABILITIES, CollaborationHub
from .collaboration_merge import merge_updates, server_merge_available
from .debug_bundle_service import build_entries
from .filesystem import FileConflictError, UnsafePathError
from .observability import (
    configure_otel,
    configure_structured_logging,
    finish_span,
    instrument_fastapi,
    request_id_context,
    start_request_span,
)
from .oidc import (
    OIDCConfig,
    OIDCState,
    authorization_url,
    discover,
    exchange_code,
    fetch_userinfo,
    validate_id_token_nonce,
)
from .project_resources import ProjectResourceService
from .provider_reviews import (
    list_provider_reviews,
    provider_repository,
)
from .retention import RetentionPolicy, cleanup_runtime_artifacts
from .review_service import create_review
from .run_comparison import duration_seconds, node_diffs, schema_timeline, stage_metric_deltas
from .run_worker import DurableRunWorker, execute_queued_local_run
from .runtime_dispatch import RuntimeDispatch
from .scheduler import ScheduleWorker, next_fire
from .settings import ServerSettings
from .storage import DataStore, RevisionConflictError


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    example: str | None = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    path: str | None = None


class ProjectUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ImportPythonRequest(BaseModel):
    path: str = "imported.py"
    source: str = Field(min_length=1)


class ImportSqlRequest(BaseModel):
    path: str = "imported.sql"
    source: str = Field(min_length=1)


class SchemaDiffRequest(BaseModel):
    before: list[dict[str, Any]]
    after: list[dict[str, Any]]
    contract_mode: str = Field(default="block", pattern=r"^(warn|block)$")
    allow_added: bool = True


class ProfileRowsRequest(BaseModel):
    rows: list[dict[str, Any]] = Field(default_factory=list, max_length=200)
    include_sensitive_metrics: bool = True
    max_rows: int = Field(default=200, ge=1, le=100_000)
    max_columns: int = Field(default=100, ge=1, le=1_000)
    top_values: int = Field(default=5, ge=0, le=100)


class ProfileDiffRequest(BaseModel):
    before: dict[str, Any]
    after: dict[str, Any]


class HistoryCheckpointRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class RedactionPreviewRequest(BaseModel):
    payload: Any


class NodeSnapshotRequest(BaseModel):
    node_id: str = Field(min_length=1, max_length=200)
    schema_: list[dict[str, Any]] | None = Field(default=None, alias="schema")
    profile: dict[str, Any] | None = None
    metrics: dict[str, Any] | None = None
    plan_artifact_id: str | None = None


class RowTraceRequest(BaseModel):
    node_id: str
    rows: list[dict[str, Any]] = Field(default_factory=list, max_length=200)
    rows_by_source: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    limit: int = Field(default=200, ge=1, le=200)


class QualityEvaluateRequest(BaseModel):
    node_id: str = Field(min_length=1, max_length=200)
    rows: list[dict[str, Any]] = Field(max_length=200)
    limit: int = Field(default=200, ge=1, le=200)


class QualitySuiteEvaluateRequest(BaseModel):
    """Bounded rows supplied by preview or a completed runtime snapshot."""

    rows_by_check: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    limit: int = Field(default=200, ge=1, le=200)
    mode: str | None = None
    automatic: bool = False


class CloneProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    remote_url: str = Field(min_length=1, max_length=2048)
    branch: str | None = Field(default=None, max_length=200)


class RunRequest(BaseModel):
    mode: str = "incremental"
    selected: list[str] = Field(default_factory=list)
    runtime_profile_id: str | None = None


class DryRunRequest(BaseModel):
    runtime_profile_id: str | None = None


class PreviewRequest(BaseModel):
    node_id: str
    limit: int = Field(default=50, ge=1, le=200)
    runtime_profile_id: str | None = None
    include_plan: bool = False
    include_profile: bool = False
    sampling_fraction: float = Field(default=1.0, gt=0, le=1)
    seed: int = Field(default=0, ge=0, le=2_147_483_647)
    timeout_seconds: int = Field(default=120, ge=1, le=600)
    cache_ttl_seconds: int = Field(default=300, ge=0, le=86_400)
    force_refresh: bool = False
    confirm_sink_test: bool = False
    profile_max_rows: int = Field(default=200, ge=1, le=100_000)
    profile_max_columns: int = Field(default=100, ge=1, le=1_000)
    profile_top_values: int = Field(default=5, ge=0, le=100)


class RuntimeProfileRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    adapter: str
    config: dict[str, Any] = Field(default_factory=dict)
    is_protected: bool = False


class RuntimeProfileUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    adapter: str | None = None
    config: dict[str, Any] | None = None
    is_protected: bool | None = None


class RuntimeProfileResponse(BaseModel):
    id: str
    name: str
    adapter: str
    config: dict[str, Any] = Field(default_factory=dict)
    is_protected: bool = False
    created_at: str | None = None
    updated_at: str | None = None


class CommitRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500)


class BranchRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class BranchDeleteRequest(BranchRequest):
    force: bool = False


class TagRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    message: str | None = Field(default=None, max_length=500)


class StashRequest(BaseModel):
    action: str = Field(pattern=r"^(list|create|apply)$")
    message: str | None = Field(default=None, max_length=500)


class ConflictResolutionRequest(BaseModel):
    path: str = Field(min_length=1, max_length=500)
    strategy: Literal["ours", "theirs"]


class GitPathsRequest(BaseModel):
    paths: list[str] = Field(default_factory=list)


class RemoteRequest(BaseModel):
    name: str = "origin"
    url: str


class GitSyncRequest(BaseModel):
    remote: str = "origin"
    branch: str | None = None


class ReviewRequest(BaseModel):
    provider: str = "auto"
    remote: str = "origin"
    title: str = Field(min_length=1, max_length=300)
    body: str = ""
    head: str
    base: str = "main"


class EventLogRequest(BaseModel):
    events: list[dict[str, Any]]


class DiagnosticRequest(BaseModel):
    error_class: str | None = None
    message: str = Field(default="", max_length=10_000)
    context: dict[str, Any] = Field(default_factory=dict)


class ExplainPlanRequest(BaseModel):
    explain: str
    before: dict[str, Any] | None = None


class ScheduleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    cron: str = Field(min_length=9, max_length=100)
    timezone: str = "UTC"
    enabled: bool = True
    runtime_profile_id: str | None = None
    mode: str = "incremental"
    concurrency_policy: str = "skip"
    missed_run_policy: str = "skip"


class GlobalScheduleRequest(ScheduleRequest):
    project_id: str


class ScheduleEnabledRequest(BaseModel):
    enabled: bool


class ScheduleUpdateRequest(BaseModel):
    enabled: bool | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)
    cron: str | None = Field(default=None, min_length=9, max_length=100)
    timezone: str | None = None
    runtime_profile_id: str | None = None
    mode: str | None = None
    concurrency_policy: str | None = None
    missed_run_policy: str | None = None


class SecretRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_.-]+$")
    value: str = Field(min_length=1)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1)


class UserRequest(BaseModel):
    username: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=12)
    role: str = "viewer"


class UserRoleRequest(BaseModel):
    role: Literal["viewer", "editor", "admin"]


class CompareRunsRequest(BaseModel):
    left_run_id: str
    right_run_id: str


def _typed_run_event(event: dict[str, Any]) -> dict[str, Any]:
    """Add the normative typed envelope while retaining legacy event fields."""
    kind = str(event.get("kind", "message"))
    event_type = {
        "status": "run.status",
        "log": "run.log",
        "problem": "run.problem",
        "metrics": "node.metrics",
    }.get(kind, f"run.{kind}")
    return {**event, "type": event_type, "payload": event.get("data", {})}


class FileWriteRequest(BaseModel):
    content: str
    etag: str | None = None


class FileRenameRequest(BaseModel):
    old_path: str = Field(min_length=1, max_length=500)
    new_path: str = Field(min_length=1, max_length=500)
    etag: str | None = None


class FileDirectoryRequest(BaseModel):
    path: str = Field(min_length=1, max_length=500)


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, HTTPException):
        return exc
    if isinstance(exc, KeyError):
        return HTTPException(status_code=404, detail="Resource not found")
    if isinstance(exc, RevisionConflictError):
        return HTTPException(
            status_code=409, detail={"message": str(exc), "current_revision": exc.current_revision}
        )
    if isinstance(exc, FileConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, UnsafePathError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


def _require_role(request: Request, minimum: str) -> None:
    rank = {"viewer": 0, "editor": 1, "admin": 2}
    identity = getattr(request.state, "identity", None)
    if identity is None:
        return
    if rank.get(str(identity.get("role")), -1) < rank[minimum]:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "SDPS-AUTH-ROLE_REQUIRED",
                "message": f"Role '{minimum}' or higher is required",
                "required_role": minimum,
            },
        )


def _audit_actor(request: Request) -> str:
    identity = getattr(request.state, "identity", None) or {}
    return str(identity.get("username") or "shared-token")


_SECRET_KEY_PARTS = ("password", "secret", "token", "credential", "private_key", "authorization")


def _redact_bundle_value(value: Any, key: str = "") -> Any:
    if isinstance(value, dict):
        return {name: _redact_bundle_value(item, str(name)) for name, item in value.items()}
    if isinstance(value, list):
        return [_redact_bundle_value(item, key) for item in value]
    if isinstance(value, str):
        if any(part in key.lower() for part in _SECRET_KEY_PARTS):
            return "***REDACTED***"
        redacted = re.sub(
            r"(?i)(bearer\s+|(?:token|password|secret|api[_-]?key)\s*[=:]\s*)[^\s,;]+",
            r"\1***REDACTED***",
            value,
        )
        return redacted
    return value


def _redact_registered_secrets(value: Any, secrets_by_name: dict[str, str]) -> tuple[Any, set[str]]:
    matched: set[str] = set()
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            redacted[key], child_matches = _redact_registered_secrets(item, secrets_by_name)
            matched.update(child_matches)
        return redacted, matched
    if isinstance(value, list):
        redacted_items = []
        for item in value:
            redacted_item, child_matches = _redact_registered_secrets(item, secrets_by_name)
            redacted_items.append(redacted_item)
            matched.update(child_matches)
        return redacted_items, matched
    if isinstance(value, str):
        redacted_text = value
        for name, secret in sorted(secrets_by_name.items()):
            if secret and secret in redacted_text:
                redacted_text = redacted_text.replace(secret, "***REDACTED***")
                matched.add(name)
        return redacted_text, matched
    return value, matched


def _websocket_protocols(ws: WebSocket) -> list[str]:
    return [
        part.strip()
        for part in ws.headers.get("sec-websocket-protocol", "").split(",")
        if part.strip()
    ]


def _decode_collaboration_update(value: str) -> bytes:
    """Decode one canonical URL-safe base64 Yjs update strictly."""
    if not value or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("Collaboration update must be URL-safe base64")
    try:
        decoded = base64.b64decode(
            value.encode("ascii") + b"=" * (-len(value) % 4), altchars=b"-_", validate=True
        )
    except (ValueError, binascii.Error) as exc:
        raise ValueError("Collaboration update must be URL-safe base64") from exc
    return decoded


def _websocket_authorized(
    ws: WebSocket, expected: str | None, auth_service: AuthService | None = None
) -> bool:
    if not expected:
        return True
    for protocol in _websocket_protocols(ws):
        if not protocol.startswith("sdpstudio.auth."):
            continue
        encoded = protocol.removeprefix("sdpstudio.auth.")
        try:
            padded = encoded + "=" * (-len(encoded) % 4)
            supplied = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            continue
        if supplied and expected and hmac.compare_digest(supplied, expected):
            return True
        if supplied and auth_service and auth_service.verify(supplied):
            return True
    return False


def _websocket_subprotocol(ws: WebSocket) -> str | None:
    return "sdpstudio.v1" if "sdpstudio.v1" in _websocket_protocols(ws) else None


def _websocket_role(ws: WebSocket, auth_service: AuthService | None) -> str | None:
    """Return the local-session role; shared bearer tokens remain editor-capable."""
    for protocol in _websocket_protocols(ws):
        if not protocol.startswith("sdpstudio.auth."):
            continue
        try:
            encoded = protocol.removeprefix("sdpstudio.auth.")
            supplied = base64.urlsafe_b64decode(
                (encoded + "=" * (-len(encoded) % 4)).encode("ascii")
            ).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            continue
        identity = auth_service.verify(supplied) if auth_service else None
        if identity:
            return str(identity.get("role"))
    return None


def _is_loopback_host(host: str) -> bool:
    """Return whether a bind host is loopback without relying on string matching."""
    normalized = host.strip().strip("[]").lower()
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        # DNS names cannot be safely classified without resolving them. Treat them
        # as remote so a hostname resolving to a LAN address cannot bypass auth.
        return False


def create_app(
    data_root: Path | None = None,
    *,
    bind_host: str = "127.0.0.1",
    allow_insecure_remote: bool = False,
) -> FastAPI:
    configure_structured_logging()
    app = FastAPI(
        title="SDP Studio API",
        version="0.1.0",
        description="Open-source visual IDE API for Apache Spark Declarative Pipelines",
    )
    settings = ServerSettings.from_env(data_root)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:8787", "http://localhost:8787"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    request_metrics: dict[str, float] = {
        "requests_total": 0,
        "responses_4xx": 0,
        "responses_5xx": 0,
        "request_duration_seconds_count": 0,
        "request_duration_seconds_sum": 0,
        "active_websockets": 0,
        "runs_queued": 0,
        "runs_running": 0,
        "worker_heartbeats_total": 0,
        "schedules_fired_total": 0,
        "codegen_total": 0,
        "preview_total": 0,
        "git_operations_total": 0,
        "codegen_duration_seconds_count": 0,
        "codegen_duration_seconds_sum": 0,
        "preview_duration_seconds_count": 0,
        "preview_duration_seconds_sum": 0,
        "git_operation_duration_seconds_count": 0,
        "git_operation_duration_seconds_sum": 0,
        "run_duration_seconds_count": 0,
        "run_duration_seconds_sum": 0,
    }
    duration_buckets = {boundary: 0 for boundary in (0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0)}
    duration_buckets[float("inf")] = 0
    operation_duration_buckets = {
        name: {boundary: 0 for boundary in duration_buckets}
        for name in ("codegen", "preview", "git_operation", "run")
    }

    @app.middleware("http")
    async def api_version_alias(request: Request, call_next):
        """Accept the versioned public API while retaining the 0.1 route names."""
        prefix = "/api/v1"
        if request.scope.get("path", "").startswith(prefix + "/"):
            request.scope["path"] = "/api" + request.scope["path"][len(prefix) :]
            request.scope["raw_path"] = request.scope["path"].encode("ascii", "ignore")
        return await call_next(request)

    auth_token = settings.auth_token
    auth_service = None
    signing_key = settings.auth_signing_key
    if signing_key:
        auth_service = AuthService(signing_key.encode())
        admin_password = settings.admin_password
        if admin_password:
            auth_service.add_user("admin", admin_password, "admin")
    oidc_config = OIDCConfig(
        issuer=settings.oidc_issuer,
        client_id=settings.oidc_client_id,
        redirect_uri=settings.oidc_redirect_uri,
        client_secret=settings.oidc_client_secret,
        token_endpoint=settings.oidc_token_endpoint,
        userinfo_endpoint=settings.oidc_userinfo_endpoint,
        jwks_uri=settings.oidc_jwks_uri,
    )
    oidc_state = OIDCState(signing_key.encode()) if signing_key else None
    # OIDC still relies on the local signing key for state and session
    # verification, so an issuer URL alone is not authentication configuration.
    team_mode = bool(settings.database_url)
    auth_configured = bool(auth_token or auth_service)
    if team_mode and not auth_configured and not allow_insecure_remote:
        raise ValueError(
            "Team mode requires authentication. Set SDPSTUDIO_AUTH_TOKEN or "
            "SDPSTUDIO_AUTH_SIGNING_KEY, or explicitly allow insecure development mode."
        )
    if not _is_loopback_host(bind_host) and not auth_configured and not allow_insecure_remote:
        raise ValueError(
            "Non-loopback binds require authentication. Set SDPSTUDIO_AUTH_TOKEN or "
            "SDPSTUDIO_AUTH_SIGNING_KEY, or explicitly allow insecure remote access."
        )
    auth_required = bool(auth_token or auth_service or team_mode)

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        started = monotonic()
        request_id = request.headers.get("x-request-id") or uuid4().hex
        context_token = request_id_context.set(request_id)
        span = start_request_span(
            "sdpstudio.http.request",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )
        protected = (
            request.url.path.startswith("/api/")
            and request.url.path
            not in {
                "/api/auth/login",
                "/api/auth/oidc/config",
                "/api/auth/oidc/start",
                "/api/auth/oidc/callback",
            }
        ) or request.url.path in {
            "/docs",
            "/redoc",
            "/openapi.json",
        }
        if auth_required and protected:
            header = request.headers.get("authorization", "")
            supplied = header[7:] if header.lower().startswith("bearer ") else ""
            cookie_token = request.cookies.get("sdpstudio_session", "")
            candidate = supplied or cookie_token
            local_identity = auth_service.verify(candidate) if auth_service and candidate else None
            shared_valid = bool(
                candidate and auth_token and hmac.compare_digest(candidate, auth_token)
            )
            if not candidate or (not shared_valid and local_identity is None):
                response = JSONResponse(
                    {"detail": "Authentication required"},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
                response.headers["x-request-id"] = request_id
                return response
            if (
                cookie_token
                and not supplied
                and request.method in {"POST", "PUT", "PATCH", "DELETE"}
            ):
                csrf_cookie = request.cookies.get("sdpstudio_csrf", "")
                csrf_header = request.headers.get("x-csrf-token", "")
                if not csrf_cookie or not hmac.compare_digest(csrf_cookie, csrf_header):
                    response = JSONResponse({"detail": "CSRF token required"}, status_code=403)
                    response.headers["x-request-id"] = request_id
                    return response
            request.state.identity = local_identity
            request.state.auth_token = candidate
        elif auth_service and protected:
            header = request.headers.get("authorization", "")
            supplied = header[7:] if header.lower().startswith("bearer ") else ""
            cookie_token = request.cookies.get("sdpstudio_session", "")
            candidate = supplied or cookie_token
            identity = auth_service.verify(candidate) if candidate else None
            if identity is None:
                response = JSONResponse({"detail": "Authentication required"}, status_code=401)
                response.headers["x-request-id"] = request_id
                return response
            if (
                cookie_token
                and not supplied
                and request.method in {"POST", "PUT", "PATCH", "DELETE"}
            ):
                csrf_cookie = request.cookies.get("sdpstudio_csrf", "")
                csrf_header = request.headers.get("x-csrf-token", "")
                if not csrf_cookie or not hmac.compare_digest(csrf_cookie, csrf_header):
                    response = JSONResponse({"detail": "CSRF token required"}, status_code=403)
                    response.headers["x-request-id"] = request_id
                    return response
            request.state.identity = identity
            request.state.auth_token = candidate
        try:
            response = await call_next(request)
        finally:
            request_id_context.reset(context_token)
        elapsed = monotonic() - started
        request_metrics["requests_total"] += 1
        request_metrics["request_duration_seconds_count"] += 1
        request_metrics["request_duration_seconds_sum"] += elapsed
        for boundary in duration_buckets:
            if elapsed <= boundary:
                duration_buckets[boundary] += 1
        path = request.url.path
        if "/generate" in path:
            request_metrics["codegen_duration_seconds_count"] += 1
            request_metrics["codegen_duration_seconds_sum"] += elapsed
        elif path.endswith("/preview"):
            request_metrics["preview_duration_seconds_count"] += 1
            request_metrics["preview_duration_seconds_sum"] += elapsed
        elif "/git/" in path:
            request_metrics["git_operation_duration_seconds_count"] += 1
            request_metrics["git_operation_duration_seconds_sum"] += elapsed
        elif path.endswith("/runs"):
            request_metrics["run_duration_seconds_count"] += 1
            request_metrics["run_duration_seconds_sum"] += elapsed
        operation_name = (
            "codegen"
            if "/generate" in path
            else "preview"
            if path.endswith("/preview")
            else "git_operation"
            if "/git/" in path
            else "run"
            if path.endswith("/runs")
            else None
        )
        if operation_name:
            for boundary in duration_buckets:
                if elapsed <= boundary:
                    operation_duration_buckets[operation_name][boundary] += 1
        finish_span(span, status_code=response.status_code, duration_seconds=elapsed)
        if response.status_code >= 500:
            request_metrics["responses_5xx"] += 1
        elif response.status_code >= 400:
            request_metrics["responses_4xx"] += 1
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; base-uri 'self'; frame-ancestors 'none'; "
            "object-src 'none'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; connect-src 'self' ws: wss:"
        )
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["x-request-id"] = request_id
        return response

    store = DataStore(data_root)
    async_store = AsyncStore(store)

    resources = ProjectResourceService(workspace_root=store.projects_root)

    async def _project_path(project_id: str) -> Path:
        return resources.resolve_project_path(await async_store.call("get_project_row", project_id))

    if auth_service:
        AuthBootstrapService(auth_service, store.load_users_for_auth, store.save_user).run(
            os.environ.get("SDPSTUDIO_ADMIN_PASSWORD")
        )
    runtime = LocalRuntime(store)
    runtime_dispatch = RuntimeDispatch(
        runtime,
        adapter=DurableLocalRuntimeAdapter(runtime),
        adapter_factory=adapter_for,
    )
    durable_worker = DurableRunWorker(
        store,
        worker_id=f"server-{os.getpid()}",
        executor=lambda record: execute_queued_local_run(store, record),
    )
    hub = CollaborationHub()
    merge_enabled = server_merge_available()

    async def dispatch_schedule(schedule: dict[str, Any]) -> None:
        profile = (
            await async_store.call("get_runtime_profile", schedule["runtime_profile_id"])
            if schedule.get("runtime_profile_id")
            else None
        )
        await runtime_dispatch.submit(schedule["project_id"], schedule["mode"], [], profile=profile)

    async def claim_schedule(schedule_id: str, marker: str) -> bool:
        return await async_store.call("claim_schedule", schedule_id, marker)

    async def list_schedules() -> list[dict[str, Any]]:
        projects = await async_store.call("list_projects")
        schedules: list[dict[str, Any]] = []
        for project in projects:
            schedules.extend(await async_store.call("list_schedules", project["id"]))
        return schedules

    scheduler = ScheduleWorker(
        list_schedules,
        dispatch_schedule,
        claim=claim_schedule,
    )
    app.state.store = store
    app.state.async_store = async_store
    app.state.runtime = runtime
    app.state.runtime_dispatch = runtime_dispatch
    app.state.durable_worker = durable_worker
    app.state.hub = hub
    app.state.files = resources
    app.state.scheduler = scheduler
    app.state.auth = auth_service
    git_locks: dict[str, asyncio.Lock] = {}
    git_mutations = {
        "init",
        "set_remote",
        "fetch",
        "pull",
        "push",
        "commit",
        "stash",
        "stage",
        "unstage",
        "create_branch",
        "switch_branch",
        "checkout",
        "resolve_conflict",
        "create_tag",
    }

    async def _git_call(method: str, project_id: str, *args: Any, **kwargs: Any) -> Any:
        """Keep subprocess-backed Git operations off the async event loop."""
        request_metrics["git_operations_total"] += 1
        path = await _project_path(project_id)
        operation = getattr(git_service, method)
        lock = git_locks.setdefault(project_id, asyncio.Lock())
        async with lock:
            if method in git_mutations:
                # Preserve the visual graph and collaboration state before a
                # worktree mutation can replace or conflict with it.
                await async_store.call(
                    "create_history_checkpoint", project_id, f"before git {method}"
                )
                document = await async_store.call("load_pipeline", project_id)
                await async_store.call(
                    "save_collaboration_snapshot", project_id, document.model_dump(by_alias=True)
                )
            return await asyncio.to_thread(operation, path, *args, **kwargs)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        configure_otel()
        instrument_fastapi(app)
        runtime.reconcile_orphaned_processes()
        await async_store.call("reconcile_non_terminal_runs")
        await scheduler.start()
        worker_stop = asyncio.Event()

        async def drain_runs() -> None:
            while not worker_stop.is_set():
                try:
                    await durable_worker.poll_once_async(lease_seconds=60)
                except Exception:
                    # The run worker records execution failures on the run;
                    # keep the server alive so another queued run can proceed.
                    await asyncio.sleep(0.25)
                else:
                    await asyncio.sleep(0.05)

        worker_task = asyncio.create_task(drain_runs())
        try:
            yield
        finally:
            worker_stop.set()
            worker_task.cancel()
            with suppress(asyncio.CancelledError):
                await worker_task
            await scheduler.stop()
            await async_store.close()

    app.router.lifespan_context = lifespan

    repo_root = Path(__file__).resolve().parents[2]
    web_root = Path(__file__).resolve().parent / "static"
    react_root = web_root / "react"
    if web_root.exists():
        app.mount("/static", StaticFiles(directory=web_root), name="static")

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "version": "0.1.0"}

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        body = "\n".join(
            [
                "# HELP sdpstudio_requests_total HTTP requests handled by SDP Studio.",
                "# TYPE sdpstudio_requests_total counter",
                f"sdpstudio_requests_total {request_metrics['requests_total']}",
                "# TYPE sdpstudio_responses_4xx counter",
                f"sdpstudio_responses_4xx {request_metrics['responses_4xx']}",
                "# TYPE sdpstudio_responses_5xx counter",
                f"sdpstudio_responses_5xx {request_metrics['responses_5xx']}",
                "# TYPE sdpstudio_request_duration_seconds histogram",
                f"sdpstudio_request_duration_seconds_count {request_metrics['request_duration_seconds_count']}",
                f"sdpstudio_request_duration_seconds_sum {request_metrics['request_duration_seconds_sum']}",
                *[
                    f'sdpstudio_request_duration_seconds_bucket{{le="{boundary if boundary != float("inf") else "+Inf"}"}} {count}'
                    for boundary, count in duration_buckets.items()
                ],
                "# TYPE sdpstudio_active_websockets gauge",
                f"sdpstudio_active_websockets {request_metrics['active_websockets']}",
                "# TYPE sdpstudio_runs_queued gauge",
                f"sdpstudio_runs_queued {request_metrics['runs_queued']}",
                "# TYPE sdpstudio_runs_running gauge",
                f"sdpstudio_runs_running {request_metrics['runs_running']}",
                "# TYPE sdpstudio_worker_heartbeats_total counter",
                f"sdpstudio_worker_heartbeats_total {request_metrics['worker_heartbeats_total']}",
                "# TYPE sdpstudio_schedules_fired_total counter",
                f"sdpstudio_schedules_fired_total {request_metrics['schedules_fired_total']}",
                "# TYPE sdpstudio_codegen_total counter",
                f"sdpstudio_codegen_total {request_metrics['codegen_total']}",
                "# TYPE sdpstudio_preview_total counter",
                f"sdpstudio_preview_total {request_metrics['preview_total']}",
                "# TYPE sdpstudio_git_operations_total counter",
                f"sdpstudio_git_operations_total {request_metrics['git_operations_total']}",
                "# TYPE sdpstudio_codegen_duration_seconds histogram",
                f"sdpstudio_codegen_duration_seconds_count {request_metrics['codegen_duration_seconds_count']}",
                f"sdpstudio_codegen_duration_seconds_sum {request_metrics['codegen_duration_seconds_sum']}",
                *[
                    f'sdpstudio_codegen_duration_seconds_bucket{{le="{boundary if boundary != float("inf") else "+Inf"}"}} {count}'
                    for boundary, count in operation_duration_buckets["codegen"].items()
                ],
                "# TYPE sdpstudio_preview_duration_seconds histogram",
                f"sdpstudio_preview_duration_seconds_count {request_metrics['preview_duration_seconds_count']}",
                f"sdpstudio_preview_duration_seconds_sum {request_metrics['preview_duration_seconds_sum']}",
                *[
                    f'sdpstudio_preview_duration_seconds_bucket{{le="{boundary if boundary != float("inf") else "+Inf"}"}} {count}'
                    for boundary, count in operation_duration_buckets["preview"].items()
                ],
                "# TYPE sdpstudio_git_operation_duration_seconds histogram",
                f"sdpstudio_git_operation_duration_seconds_count {request_metrics['git_operation_duration_seconds_count']}",
                f"sdpstudio_git_operation_duration_seconds_sum {request_metrics['git_operation_duration_seconds_sum']}",
                *[
                    f'sdpstudio_git_operation_duration_seconds_bucket{{le="{boundary if boundary != float("inf") else "+Inf"}"}} {count}'
                    for boundary, count in operation_duration_buckets["git_operation"].items()
                ],
                "# TYPE sdpstudio_run_duration_seconds histogram",
                f"sdpstudio_run_duration_seconds_count {request_metrics['run_duration_seconds_count']}",
                f"sdpstudio_run_duration_seconds_sum {request_metrics['run_duration_seconds_sum']}",
                *[
                    f'sdpstudio_run_duration_seconds_bucket{{le="{boundary if boundary != float("inf") else "+Inf"}"}} {count}'
                    for boundary, count in operation_duration_buckets["run"].items()
                ],
                "",
            ]
        )
        return Response(content=body, media_type="text/plain; version=0.0.4")

    def _cookie_secure(request: Request) -> bool:
        """Use secure cookies for HTTPS, with an explicit deployment override."""
        forwarded = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip()
        return settings.cookie_secure or request.url.scheme == "https" or forwarded == "https"

    @app.post("/api/auth/login")
    async def login(req: LoginRequest, request: Request, response: Response) -> dict[str, Any]:
        if auth_service is None:
            raise HTTPException(status_code=503, detail="Local authentication is not configured")
        token = auth_service.login(req.username, req.password)
        if token is None:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        await async_store.call(
            "append_audit_event", req.username, "auth.login", "user", req.username
        )
        csrf = secrets.token_urlsafe(32)
        response.set_cookie(
            "sdpstudio_session",
            token,
            httponly=True,
            secure=_cookie_secure(request),
            samesite="lax",
            max_age=3600,
            path="/",
        )
        response.set_cookie(
            "sdpstudio_csrf",
            csrf,
            httponly=False,
            secure=_cookie_secure(request),
            samesite="lax",
            max_age=3600,
            path="/",
        )
        return {"username": req.username, "authenticated": True}

    @app.post("/api/auth/logout", status_code=204)
    async def logout(request: Request, response: Response) -> None:
        token = getattr(request.state, "auth_token", "")
        actor = _audit_actor(request)
        if auth_service and token:
            auth_service.revoke(token)
        await async_store.call("append_audit_event", actor, "auth.logout", "session", actor)
        response.delete_cookie("sdpstudio_session", path="/")
        response.delete_cookie("sdpstudio_csrf", path="/")

    @app.get("/api/auth/oidc/config")
    async def oidc_public_config() -> dict[str, object]:
        return oidc_config.public()

    @app.get("/api/auth/oidc/start")
    async def oidc_start(return_to: str = "/") -> dict[str, str]:
        if not oidc_state or not oidc_config.enabled:
            raise HTTPException(status_code=503, detail="OIDC is not configured")
        state = oidc_state.issue(return_to)
        payload = oidc_state.verify(state)
        assert payload is not None
        return {
            "authorization_url": authorization_url(oidc_config, state, payload["nonce"]),
            "state": state,
        }

    @app.get("/api/auth/oidc/callback")
    async def oidc_callback(
        code: str, state: str, request: Request, response: Response
    ) -> dict[str, Any]:
        if not oidc_state or not oidc_config.enabled:
            raise HTTPException(status_code=503, detail="OIDC is not configured")
        state_payload = oidc_state.consume(state)
        if not code or state_payload is None:
            raise HTTPException(status_code=400, detail="Invalid or expired OIDC state")
        try:
            resolved_oidc = (
                await asyncio.to_thread(discover, oidc_config)
                if not oidc_config.jwks_uri
                else oidc_config
            )
            token_response = await asyncio.to_thread(exchange_code, resolved_oidc, code)
            validate_id_token_nonce(
                token_response,
                state_payload["nonce"],
                expected_issuer=resolved_oidc.issuer,
                expected_audience=resolved_oidc.client_id,
                jwks_uri=resolved_oidc.jwks_uri,
            )
            access_token = str(token_response["access_token"])
            claims = await asyncio.to_thread(fetch_userinfo, resolved_oidc, access_token)
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=502, detail="OIDC identity exchange failed") from exc
        subject = str(claims.get("sub") or claims.get("email") or "")
        if not subject or auth_service is None:
            raise HTTPException(status_code=502, detail="OIDC identity did not contain a subject")
        username = str(claims.get("email") or claims.get("preferred_username") or subject)
        username = username.replace("@", "_")
        users = await async_store.call("list_users")
        existing = next((item for item in users if item["username"] == username), None)
        role = str(existing["role"]) if existing else "viewer"
        if existing is None:
            # OIDC users do not receive a local password; they authenticate only through OIDC.
            password_hash = AuthService.hash_password(secrets.token_urlsafe(24))
            auth_service.add_hashed_user(username, password_hash, role)
            await async_store.call("save_user", username, role, password_hash)
        session_token = auth_service.issue_session(username, role)
        csrf = secrets.token_urlsafe(32)
        response.set_cookie(
            "sdpstudio_session",
            session_token,
            httponly=True,
            secure=_cookie_secure(request),
            samesite="lax",
            max_age=3600,
            path="/",
        )
        response.set_cookie(
            "sdpstudio_csrf",
            csrf,
            httponly=False,
            secure=_cookie_secure(request),
            samesite="lax",
            max_age=3600,
            path="/",
        )
        return {"username": username, "role": role}

    @app.get("/api/auth/me")
    async def me(request: Request) -> dict[str, Any]:
        identity = getattr(request.state, "identity", None)
        if identity is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        return identity

    @app.get("/api/auth/users")
    async def list_users(request: Request) -> list[dict[str, Any]]:
        _require_role(request, "admin")
        return await async_store.call("list_users")

    @app.get("/api/auth/audit")
    async def audit_events(request: Request, limit: int = 100) -> list[dict[str, Any]]:
        _require_role(request, "admin")
        return await async_store.call("list_audit_events", limit)

    @app.post("/api/auth/users")
    async def create_user(req: UserRequest, request: Request) -> dict[str, Any]:
        _require_role(request, "admin")
        if auth_service is None:
            raise HTTPException(status_code=503, detail="Local authentication is not configured")
        user = auth_service.add_user(req.username, req.password, req.role)
        saved = await async_store.call("save_user", user.username, user.role, user.password_hash)
        await async_store.call(
            "append_audit_event",
            _audit_actor(request),
            "user.created",
            "user",
            user.username,
            {"role": user.role},
        )
        return saved

    @app.patch("/api/auth/users/{username}")
    async def update_user_role(
        username: str, req: UserRoleRequest, request: Request
    ) -> dict[str, Any]:
        _require_role(request, "admin")
        if auth_service is None:
            raise HTTPException(status_code=503, detail="Local authentication is not configured")
        try:
            users = await async_store.call("load_users_for_auth")
            current = next(item for item in users if item["username"] == username)
            auth_service.add_hashed_user(username, current["password_hash"], req.role)
            saved = await async_store.call("update_user_role", username, req.role)
            await async_store.call(
                "append_audit_event",
                _audit_actor(request),
                "user.role_changed",
                "user",
                username,
                {"role": req.role},
            )
            return saved
        except (KeyError, StopIteration) as exc:
            raise HTTPException(status_code=404, detail="User not found") from exc
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.get("/ready")
    async def readiness() -> dict[str, Any]:
        checks: dict[str, str] = {}
        try:
            await async_store.call("health_check")
            checks["database"] = "ok"
        except Exception:
            checks["database"] = "error"
        checks["storage"] = "ok" if resources.workspace_available() else "error"
        ready = all(value == "ok" for value in checks.values())
        return {"status": "ok" if ready else "not_ready", "checks": checks}

    @app.get("/api/operators")
    async def operators() -> list[dict[str, Any]]:
        return BUILTIN_OPERATORS

    @app.get("/api/plugins")
    async def plugins() -> dict[str, list[dict[str, Any]]]:
        """Expose compatible optional extensions without loading secrets/config."""
        result: dict[str, list[dict[str, Any]]] = {}
        for kind in PLUGIN_GROUPS:
            loaded = await asyncio.to_thread(discover_plugins, kind)
            result[kind] = [
                {
                    "name": name,
                    "manifest": getattr(plugin, "manifest", {})
                    if not isinstance(plugin, dict)
                    else plugin.get("manifest", {}),
                }
                for name, plugin in sorted(loaded.items())
            ]
        return result

    @app.get("/api/schema/pipeline")
    async def pipeline_schema() -> dict[str, Any]:
        """Expose the persisted contract to typed frontend/operator tooling."""
        return PipelineDocument.model_json_schema(by_alias=True)

    @app.post("/api/import/python")
    async def import_python(req: ImportPythonRequest) -> dict[str, Any]:
        try:
            report = discover_python(Path(req.path), req.source)
            return {
                "declarations": [item.__dict__ for item in report.declarations],
                "unsupported": list(report.unsupported),
                "source_sha256": report.source_sha256,
                "custom_code": [item.__dict__ for item in report.custom_code],
            }
        except SyntaxError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "SDPS-IMPORT-001",
                    "message": "Python source could not be parsed",
                    "line": exc.lineno,
                },
            ) from exc

    @app.post("/api/import/sql")
    async def import_sql(req: ImportSqlRequest) -> dict[str, Any]:
        report = discover_sql(Path(req.path), req.source)
        return {
            "declarations": [item.__dict__ for item in report.declarations],
            "source_sha256": report.source_sha256,
            "custom_code": [item.__dict__ for item in report.custom_code],
        }

    @app.post("/api/projects/{project_id}/import/python")
    async def import_project_python(project_id: str, req: ImportPythonRequest) -> dict[str, Any]:
        """Project-scoped alias that confirms ownership before importing source."""
        try:
            await async_store.call("get_project", project_id)
            return await import_python(req)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/projects/{project_id}/import/sql")
    async def import_project_sql(project_id: str, req: ImportSqlRequest) -> dict[str, Any]:
        try:
            await async_store.call("get_project", project_id)
            return await import_sql(req)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/projects/{project_id}/reconcile/python")
    async def reconcile_project_python(
        project_id: str, req: ImportPythonRequest, request: Request
    ) -> dict[str, Any]:
        try:
            _require_role(request, "editor")
            document = await async_store.call("load_pipeline", project_id)
            result = reconcile_python(document, req.source)
            if result.ownership == "visual" and result.changed:
                await asyncio.to_thread(store.save_pipeline, project_id, result.document)
            return {
                "ownership": result.ownership,
                "changed": result.changed and result.ownership == "visual",
                "document": result.document.model_dump(by_alias=True),
                "problems": [problem.__dict__ for problem in result.problems],
                "regions": [region.__dict__ for region in result.regions],
            }
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/projects/{project_id}/reconcile/sql")
    async def reconcile_project_sql(
        project_id: str, req: ImportSqlRequest, request: Request
    ) -> dict[str, Any]:
        try:
            _require_role(request, "editor")
            document = await async_store.call("load_pipeline", project_id)
            result = reconcile_sql(document, req.source)
            if result.ownership == "visual" and result.changed:
                await asyncio.to_thread(store.save_pipeline, project_id, result.document)
            return {
                "ownership": result.ownership,
                "changed": result.changed and result.ownership == "visual",
                "document": result.document.model_dump(by_alias=True),
                "problems": [problem.__dict__ for problem in result.problems],
                "regions": [region.__dict__ for region in result.regions],
            }
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/projects/{project_id}/import")
    async def import_project(project_id: str, req: ImportPythonRequest) -> dict[str, Any]:
        """Default project import targets Python, matching the CLI default."""
        return await import_project_python(project_id, req)

    @app.post("/api/debug/schema-diff")
    async def debug_schema_diff(req: SchemaDiffRequest) -> dict[str, Any]:
        return {
            "before_fingerprint": schema_fingerprint(req.before),
            "after_fingerprint": schema_fingerprint(req.after),
            "diff": schema_diff(req.before, req.after),
            "contract": evaluate_schema_contract(
                schema_diff(req.before, req.after),
                mode=req.contract_mode,
                allow_added=req.allow_added,
            ),
        }

    @app.post("/api/debug/profile")
    async def debug_profile(req: ProfileRowsRequest) -> dict[str, Any]:
        return profile_rows(
            req.rows,
            include_sensitive_metrics=req.include_sensitive_metrics,
            max_rows=req.max_rows,
            max_columns=req.max_columns,
            top_values=req.top_values,
        )

    @app.post("/api/debug/profile-diff")
    async def debug_profile_diff(req: ProfileDiffRequest) -> dict[str, Any]:
        return profile_diff(req.before, req.after)

    @app.get("/api/doctor")
    async def doctor() -> dict[str, Any]:
        return probe_local().model_dump()

    @app.get("/api/runtime-profiles", response_model=list[RuntimeProfileResponse])
    async def runtime_profiles() -> list[RuntimeProfileResponse]:
        return await async_store.call("list_runtime_profiles")

    @app.post("/api/runtime-profiles", response_model=RuntimeProfileResponse)
    async def create_runtime_profile(
        req: RuntimeProfileRequest, request: Request
    ) -> dict[str, Any]:
        try:
            # Provider profiles can grant access to external namespaces and
            # workspaces; only administrators may create those bindings.
            _require_role(
                request,
                "admin" if req.adapter in {"kubernetes", "databricks"} else "editor",
            )
            result = await async_store.call(
                "create_runtime_profile",
                req.name,
                req.adapter,
                req.config,
                is_protected=req.is_protected,
            )
            await async_store.call(
                "append_audit_event",
                _audit_actor(request),
                "runtime_profile.created",
                "runtime_profile",
                result["id"],
                {"adapter": req.adapter},
            )
            return result
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.delete("/api/runtime-profiles/{profile_id}", status_code=204)
    async def delete_runtime_profile(profile_id: str, request: Request) -> None:
        try:
            profile = await async_store.call("get_runtime_profile", profile_id)
            _require_role(
                request,
                "admin"
                if profile.get("adapter") in {"kubernetes", "databricks"}
                or profile.get("is_protected")
                else "editor",
            )
            await async_store.call("delete_runtime_profile", profile_id)
            await async_store.call(
                "append_audit_event",
                _audit_actor(request),
                "runtime_profile.deleted",
                "runtime_profile",
                profile_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.patch("/api/runtime-profiles/{profile_id}", response_model=RuntimeProfileResponse)
    async def update_runtime_profile(
        profile_id: str, req: RuntimeProfileUpdateRequest, request: Request
    ) -> dict[str, Any]:
        try:
            _require_role(request, "admin")
            result = await async_store.call(
                "update_runtime_profile",
                profile_id,
                name=req.name,
                adapter=req.adapter,
                config=req.config,
                is_protected=req.is_protected,
            )
            await async_store.call(
                "append_audit_event",
                _audit_actor(request),
                "runtime_profile.changed",
                "runtime_profile",
                profile_id,
                {"adapter": result["adapter"]},
            )
            return result
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.get("/api/runtime-profiles/{profile_id}", response_model=RuntimeProfileResponse)
    async def get_runtime_profile(profile_id: str) -> RuntimeProfileResponse:
        try:
            return await async_store.call("get_runtime_profile", profile_id)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.get("/api/runtime-profiles/{profile_id}/probe")
    async def probe_runtime_profile(profile_id: str) -> dict[str, Any]:
        try:
            profile = await async_store.call("get_runtime_profile", profile_id)
            return probe_profile(profile).model_dump()
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/runtime-profiles/{profile_id}/test")
    async def test_runtime_profile(profile_id: str, request: Request) -> dict[str, Any]:
        try:
            _require_role(request, "editor")
            profile = await async_store.call("get_runtime_profile", profile_id)
            result = probe_profile(profile).model_dump()
            if profile.get("adapter") == "kubernetes":
                result["live_cluster"] = await asyncio.to_thread(probe_kubernetes_live, profile)
            return result
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.get("/api/projects", response_model=list[ProjectResponse])
    async def list_projects() -> list[dict[str, Any]]:
        return await async_store.call("list_projects")

    @app.post("/api/projects", response_model=ProjectResponse)
    async def create_project(req: CreateProjectRequest, request: Request) -> dict[str, Any]:
        try:
            _require_role(request, "editor")
            example = repo_root / "examples" / req.example if req.example else None
            project = await async_store.call("create_project", req.name, example_path=example)
            await async_store.call(
                "append_audit_event",
                _audit_actor(request),
                "project.created",
                "project",
                project["id"],
            )
            return project
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/projects/clone")
    async def clone_project(req: CloneProjectRequest, request: Request) -> dict[str, Any]:
        try:
            _require_role(request, "editor")
            return await async_store.call("clone_project", req.name, req.remote_url, req.branch)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.get("/api/projects/{project_id}")
    async def get_project(project_id: str) -> dict[str, Any]:
        try:
            return await async_store.call("get_project", project_id)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.patch("/api/projects/{project_id}")
    async def update_project(
        project_id: str, req: ProjectUpdateRequest, request: Request
    ) -> dict[str, Any]:
        try:
            _require_role(request, "editor")
            project = await async_store.call("update_project", project_id, req.name)
            await async_store.call(
                "append_audit_event",
                _audit_actor(request),
                "project.updated",
                "project",
                project_id,
            )
            return project
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.delete("/api/projects/{project_id}", status_code=204)
    async def delete_project(project_id: str, request: Request) -> None:
        try:
            _require_role(request, "editor")
            await async_store.call("delete_project", project_id)
            await async_store.call(
                "append_audit_event",
                _audit_actor(request),
                "project.deleted",
                "project",
                project_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.get("/api/projects/{project_id}/pipeline")
    async def get_pipeline(project_id: str) -> dict[str, Any]:
        try:
            pipeline = await async_store.call("load_pipeline", project_id)
            return pipeline.model_dump(by_alias=True)
        except Exception as exc:
            raise _http_error(exc) from exc

    def _pipeline_resource(project_id: str, document: PipelineDocument) -> dict[str, Any]:
        return {
            "id": project_id,
            "project_id": project_id,
            **document.model_dump(by_alias=True),
        }

    @app.get("/api/projects/{project_id}/pipelines")
    async def list_pipelines(project_id: str) -> list[dict[str, Any]]:
        try:
            document = await async_store.call("load_pipeline", project_id)
            return [_pipeline_resource(project_id, document)]
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.get("/api/projects/{project_id}/schedules")
    async def list_project_schedules(project_id: str) -> list[dict[str, Any]]:
        try:
            await async_store.call("get_project_row", project_id)
            schedules = await async_store.call("list_schedules", project_id)
            for schedule in schedules:
                fire = (
                    next_fire(schedule["cron"], datetime.now().astimezone(), schedule["timezone"])
                    if schedule.get("enabled")
                    else None
                )
                schedule["next_fire"] = fire.isoformat() if fire is not None else None
            return schedules
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.get("/api/schedules")
    async def list_all_schedules() -> list[dict[str, Any]]:
        """List schedules across projects for scheduler administration."""
        try:
            projects = await async_store.call("list_projects")
            schedules: list[dict[str, Any]] = []
            for project in projects:
                schedules.extend(await list_project_schedules(str(project["id"])))
            return schedules
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.get("/api/secrets")
    async def list_secrets(request: Request) -> list[dict[str, Any]]:
        try:
            _require_role(request, "admin")
            return await async_store.call("list_secrets")
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/secrets")
    async def create_secret(req: SecretRequest, request: Request) -> dict[str, Any]:
        """Create or rotate a registered secret through the normative route."""
        return await put_secret(req.name, req, request)

    @app.put("/api/secrets/{name}")
    async def put_secret(name: str, req: SecretRequest, request: Request) -> dict[str, Any]:
        _require_role(request, "admin")
        if name != req.name:
            raise HTTPException(status_code=400, detail="Secret name mismatch")
        try:
            result = await async_store.call("put_secret", name, req.value)
            await async_store.call(
                "append_audit_event", _audit_actor(request), "secret.changed", "secret", name
            )
            return result
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/secrets/rotate-key")
    async def rotate_secret_key(request: Request) -> dict[str, Any]:
        """Re-encrypt registered secrets with the active out-of-band key."""
        _require_role(request, "admin")
        try:
            result = await async_store.call("rotate_secrets")
            await async_store.call(
                "append_audit_event",
                _audit_actor(request),
                "secret.key_rotated",
                "secret",
                "*",
                {"rotated": result["rotated"], "key_id": result["key_id"]},
            )
            return result
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.delete("/api/secrets/{secret_id}", status_code=204)
    async def delete_secret(secret_id: str, request: Request) -> None:
        try:
            _require_role(request, "admin")
            await async_store.call("delete_secret", secret_id)
            await async_store.call(
                "append_audit_event", _audit_actor(request), "secret.deleted", "secret", secret_id
            )
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/projects/{project_id}/schedules")
    async def create_schedule(
        project_id: str, req: ScheduleRequest, request: Request
    ) -> dict[str, Any]:
        try:
            _require_role(request, "editor")
            result = await async_store.call("create_schedule", project_id, **req.model_dump())
            await async_store.call(
                "append_audit_event",
                _audit_actor(request),
                "schedule.created",
                "schedule",
                result["id"],
            )
            return result
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/schedules")
    async def create_global_schedule(
        req: GlobalScheduleRequest, request: Request
    ) -> dict[str, Any]:
        """Create a schedule using the normative global administration route."""
        try:
            _require_role(request, "editor")
            await async_store.call("get_project_row", req.project_id)
            payload = req.model_dump(exclude={"project_id"})
            result = await async_store.call("create_schedule", req.project_id, **payload)
            await async_store.call(
                "append_audit_event",
                _audit_actor(request),
                "schedule.created",
                "schedule",
                result["id"],
            )
            return result
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/projects/{project_id}/schedules/{schedule_id}/run-now")
    async def run_schedule_now(
        project_id: str, schedule_id: str, request: Request
    ) -> dict[str, Any]:
        """Submit a schedule immediately while preserving its runtime profile policy."""
        try:
            _require_role(request, "editor")
            schedule = await async_store.call("get_schedule", schedule_id)
            if schedule["project_id"] != project_id:
                raise ValueError("Schedule does not belong to this project")
            profile = (
                await async_store.call("get_runtime_profile", schedule["runtime_profile_id"])
                if schedule.get("runtime_profile_id")
                else None
            )
            if profile and profile.get("is_protected"):
                _require_role(request, "admin")
            record = await runtime_dispatch.submit(
                project_id, schedule["mode"], [], profile=profile
            )
            result = await async_store.call("get_run", record.id)
            await async_store.call(
                "append_audit_event",
                _audit_actor(request),
                "schedule.run_now",
                "schedule",
                schedule_id,
                {
                    "project_id": project_id,
                    "run_id": record.id,
                    "protected": bool(profile and profile.get("is_protected")),
                },
            )
            return result
        except HTTPException:
            raise
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.patch("/api/schedules/{schedule_id}")
    async def update_schedule(
        schedule_id: str, req: ScheduleUpdateRequest, request: Request
    ) -> dict[str, Any]:
        try:
            _require_role(request, "editor")
            result = await async_store.call(
                "update_schedule", schedule_id, req.model_dump(exclude_none=True)
            )
            await async_store.call(
                "append_audit_event",
                _audit_actor(request),
                "schedule.changed",
                "schedule",
                schedule_id,
                req.model_dump(exclude_none=True),
            )
            return result
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.delete("/api/schedules/{schedule_id}", status_code=204)
    async def delete_schedule(schedule_id: str, request: Request) -> None:
        try:
            _require_role(request, "editor")
            await async_store.call("delete_schedule", schedule_id)
            await async_store.call(
                "append_audit_event",
                _audit_actor(request),
                "schedule.deleted",
                "schedule",
                schedule_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.get("/api/projects/{project_id}/files")
    async def file_tree(project_id: str) -> list[dict[str, Any]]:
        try:
            project = await _project_path(project_id)
            return [item.__dict__ for item in await asyncio.to_thread(resources.tree, project)]
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.get("/api/projects/{project_id}/tree")
    async def project_tree(project_id: str) -> list[dict[str, Any]]:
        """Normative alias for the project explorer tree."""
        return await file_tree(project_id)

    @app.get("/api/projects/{project_id}/files/{path:path}")
    async def read_file(project_id: str, path: str) -> dict[str, Any]:
        try:
            project = await _project_path(project_id)
            content, info = await asyncio.to_thread(resources.read_text, project, path)
            return {"path": info.path, "content": content, "etag": info.etag, "size": info.size}
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.put("/api/projects/{project_id}/files/{path:path}")
    async def write_file(
        project_id: str, path: str, req: FileWriteRequest, request: Request
    ) -> dict[str, Any]:
        try:
            _require_role(request, "editor")
            project = await _project_path(project_id)
            info = await asyncio.to_thread(
                resources.write_text, project, path, req.content, req.etag
            )
            return info.__dict__
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/projects/{project_id}/files/directory")
    async def create_directory(
        project_id: str, req: FileDirectoryRequest, request: Request
    ) -> dict[str, Any]:
        try:
            _require_role(request, "editor")
            project = await _project_path(project_id)
            info = await asyncio.to_thread(resources.create_directory, project, req.path)
            return info.__dict__
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/projects/{project_id}/files/rename")
    async def rename_file(
        project_id: str, req: FileRenameRequest, request: Request
    ) -> dict[str, Any]:
        try:
            _require_role(request, "editor")
            project = await _project_path(project_id)
            info = await asyncio.to_thread(
                resources.rename, project, req.old_path, req.new_path, req.etag
            )
            return info.__dict__
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.delete("/api/projects/{project_id}/files/{path:path}", status_code=204)
    async def delete_file(
        project_id: str, path: str, request: Request, etag: str | None = None
    ) -> None:
        try:
            _require_role(request, "editor")
            project = await _project_path(project_id)
            await asyncio.to_thread(resources.delete, project, path, etag)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.put("/api/projects/{project_id}/pipeline")
    async def save_pipeline(
        project_id: str, document: PipelineDocument, request: Request
    ) -> dict[str, Any]:
        try:
            _require_role(request, "editor")
            saved = await async_store.call("save_pipeline", project_id, document)
            event = await async_store.call(
                "append_collaboration_event",
                project_id,
                {
                    "type": "pipeline_saved",
                    "revision": saved.revision,
                    "client_id": request.headers.get("x-sdpstudio-client-id"),
                },
            )
            await async_store.call(
                "save_collaboration_snapshot",
                project_id,
                saved.model_dump(by_alias=True),
                seq=event["seq"],
            )
            if event["seq"] >= 50 and event["seq"] % 25 == 0:
                await async_store.call(
                    "compact_collaboration_events", project_id, max(1, event["seq"] - 25)
                )
            await hub.broadcast(project_id, event)
            await async_store.call(
                "append_audit_event",
                _audit_actor(request),
                "pipeline.saved",
                "project",
                project_id,
                {"revision": saved.revision},
            )
            return saved.model_dump(by_alias=True)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/projects/{project_id}/pipelines")
    async def create_pipeline(
        project_id: str, document: PipelineDocument, request: Request
    ) -> dict[str, Any]:
        saved = await save_pipeline(project_id, document, request)
        return _pipeline_resource(project_id, PipelineDocument.model_validate(saved))

    @app.get("/api/pipelines/{pipeline_id}")
    async def get_pipeline_resource(pipeline_id: str) -> dict[str, Any]:
        document = await get_pipeline(pipeline_id)
        return _pipeline_resource(pipeline_id, PipelineDocument.model_validate(document))

    @app.put("/api/pipelines/{pipeline_id}")
    async def update_pipeline_resource(
        pipeline_id: str, document: PipelineDocument, request: Request
    ) -> dict[str, Any]:
        saved = await save_pipeline(pipeline_id, document, request)
        return _pipeline_resource(pipeline_id, PipelineDocument.model_validate(saved))

    @app.post("/api/pipelines/{pipeline_id}/validate")
    async def validate_pipeline_resource(pipeline_id: str) -> dict[str, Any]:
        return await validate(pipeline_id)

    @app.post("/api/pipelines/{pipeline_id}/preview")
    async def preview_pipeline_resource(pipeline_id: str, req: PreviewRequest) -> dict[str, Any]:
        return await preview(pipeline_id, req)

    @app.get("/api/pipelines/{pipeline_id}/compatibility")
    async def pipeline_compatibility(pipeline_id: str) -> dict[str, Any]:
        document = await async_store.call("load_pipeline", pipeline_id)
        capabilities = await asyncio.to_thread(probe_local)
        problems = await asyncio.to_thread(validate_capabilities, document, capabilities)
        return {
            "compatible": not any(problem.severity == "error" for problem in problems),
            "capabilities": capabilities.model_dump(),
            "problems": [problem.model_dump() for problem in problems],
        }

    @app.post("/api/projects/{project_id}/validate")
    async def validate(project_id: str) -> dict[str, Any]:
        try:
            document = await async_store.call("load_pipeline", project_id)
            graph_problems = await asyncio.to_thread(validate_graph, document)
            generated = await async_store.call("generate", project_id, write=False)
            by_key: dict[tuple[str, str | None, str], dict[str, Any]] = {}
            for problem in [*graph_problems, *generated.problems]:
                by_key[(problem.code, problem.node_id, problem.message)] = problem.model_dump()
            problems = list(by_key.values())
            return {
                "valid": not any(p["severity"] == "error" for p in problems),
                "problems": problems,
            }
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/projects/{project_id}/validate-model")
    async def validate_model(project_id: str) -> dict[str, Any]:
        """Normative alias for visual-model validation."""
        return await validate(project_id)

    @app.post("/api/projects/{project_id}/validate-capabilities")
    async def validate_runtime_capabilities(
        project_id: str, capabilities: RuntimeCapabilities
    ) -> dict[str, Any]:
        try:
            document = await async_store.call("load_pipeline", project_id)
            problems = await asyncio.to_thread(validate_capabilities, document, capabilities)
            return {
                "valid": not any(problem.severity == "error" for problem in problems),
                "problems": [problem.model_dump() for problem in problems],
            }
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/projects/{project_id}/generate")
    async def generate(project_id: str, request: Request) -> GenerationResult:
        try:
            _require_role(request, "editor")
            request_metrics["codegen_total"] += 1
            result = await async_store.call("generate", project_id, write=True)
            return result
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/projects/{project_id}/generate-sql")
    async def generate_sql(project_id: str, request: Request) -> GenerationResult:
        try:
            _require_role(request, "editor")
            request_metrics["codegen_total"] += 1
            result = await async_store.call("generate_sql", project_id, write=True)
            return result
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.get("/api/projects/{project_id}/code")
    async def code(project_id: str) -> dict[str, str]:
        try:
            return {"content": await async_store.call("generated_code", project_id)}
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.get("/api/projects/{project_id}/catalog")
    async def catalog(project_id: str, runtime_profile_id: str | None = None) -> dict[str, Any]:
        try:
            project = await _project_path(project_id)
            if runtime_profile_id:
                profile = await async_store.call("get_runtime_profile", runtime_profile_id)
                return await asyncio.to_thread(resources.runtime_catalog, profile, project)
            return await asyncio.to_thread(resources.catalog, project)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/projects/{project_id}/retention/cleanup")
    async def cleanup_project_retention(project_id: str, request: Request) -> dict[str, object]:
        """Apply configured runtime-artifact retention as an administrator."""
        try:
            _require_role(request, "admin")
            project = await _project_path(project_id)
            policy = RetentionPolicy.from_env()
            return await asyncio.to_thread(cleanup_runtime_artifacts, project, policy)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/projects/{project_id}/preview")
    async def preview(project_id: str, req: PreviewRequest) -> dict[str, Any]:
        try:
            request_metrics["preview_total"] += 1
            profile = (
                await async_store.call("get_runtime_profile", req.runtime_profile_id)
                if req.runtime_profile_id
                else None
            )
            return await runtime_dispatch.preview(
                project_id,
                req.node_id,
                req.limit,
                profile=profile,
                include_plan=req.include_plan,
                include_profile=req.include_profile,
                sampling_fraction=req.sampling_fraction,
                seed=req.seed,
                timeout_seconds=req.timeout_seconds,
                cache_ttl_seconds=req.cache_ttl_seconds,
                force_refresh=req.force_refresh,
                confirm_sink_test=req.confirm_sink_test,
                profile_max_rows=req.profile_max_rows,
                profile_max_columns=req.profile_max_columns,
                profile_top_values=req.profile_top_values,
            )
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/projects/{project_id}/dry-run")
    async def dry_run(
        project_id: str, request: Request, req: DryRunRequest | None = None
    ) -> dict[str, Any]:
        try:
            _require_role(request, "editor")
            result = await async_store.call("generate", project_id, write=True)
            if any(p.severity == "error" for p in result.problems):
                return {"ok": False, "problems": [p.model_dump() for p in result.problems]}
            profile = (
                await async_store.call("get_runtime_profile", req.runtime_profile_id)
                if req and req.runtime_profile_id
                else None
            )
            return await runtime_dispatch.dry_run(project_id, profile=profile)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/projects/{project_id}/runs")
    async def start_run(project_id: str, req: RunRequest, request: Request) -> dict[str, Any]:
        try:
            _require_role(request, "editor")
            result = await async_store.call("generate", project_id, write=True)
            if any(p.severity == "error" for p in result.problems):
                raise HTTPException(
                    status_code=422, detail=[p.model_dump() for p in result.problems]
                )
            profile = (
                await async_store.call("get_runtime_profile", req.runtime_profile_id)
                if req.runtime_profile_id
                else None
            )
            if profile and profile.get("is_protected"):
                _require_role(request, "admin")
            record = await runtime_dispatch.submit(
                project_id,
                req.mode,
                req.selected,
                profile=profile,
                defer_execution=True,
            )
            result = await async_store.call("get_run", record.id)
            await async_store.call(
                "append_audit_event",
                _audit_actor(request),
                "run.started",
                "run",
                record.id,
                {
                    "project_id": project_id,
                    "mode": req.mode,
                    "protected": bool(profile and profile.get("is_protected")),
                },
            )
            return result
        except HTTPException:
            raise
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/pipelines/{pipeline_id}/runs")
    async def start_pipeline_run(
        pipeline_id: str, req: RunRequest, request: Request
    ) -> dict[str, Any]:
        return await start_run(pipeline_id, req, request)

    @app.get("/api/projects/{project_id}/runs")
    async def list_runs(project_id: str) -> list[dict[str, Any]]:
        try:
            return await async_store.call("list_runs", project_id)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.get("/api/runs/{run_id}/node-snapshots")
    async def list_node_snapshots(run_id: str) -> list[dict[str, Any]]:
        try:
            await async_store.call("get_run", run_id)
            return await async_store.call("get_node_snapshots", run_id)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.get("/api/runs/{run_id}/plan")
    async def get_run_plan(run_id: str) -> dict[str, Any]:
        """Return the captured Spark plan artifact for a completed or running run."""
        try:
            run = await async_store.call("get_run", run_id)
            project = await _project_path(str(run["project_id"]))
            artifact = project / ".sdpstudio" / "runtime" / "run-artifacts" / run_id / "plan.json"
            if not artifact.is_file():
                raise KeyError("plan")
            return json.loads(artifact.read_text(encoding="utf-8"))
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.get("/api/runs/{run_id}/nodes/{node_id}")
    async def get_run_node(run_id: str, node_id: str) -> dict[str, Any]:
        """Return one persisted node snapshot for run-detail tooling."""
        try:
            await async_store.call("get_run", run_id)
            snapshots = await async_store.call("get_node_snapshots", run_id)
            for snapshot in snapshots:
                if str(snapshot.get("node_id")) == node_id:
                    return snapshot
            raise KeyError(node_id)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/projects/{project_id}/runs/{run_id}/node-snapshots")
    async def save_node_snapshot(
        project_id: str, run_id: str, req: NodeSnapshotRequest, request: Request
    ) -> dict[str, Any]:
        try:
            _require_role(request, "editor")
            run = await async_store.call("get_run", run_id)
            if run["project_id"] != project_id:
                raise ValueError("Run does not belong to this project")
            return await async_store.call(
                "save_node_snapshot",
                run_id,
                req.node_id,
                schema=req.schema_,
                profile=req.profile,
                metrics=req.metrics,
                plan_artifact_id=req.plan_artifact_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.get("/api/runs/{run_id}")
    async def get_run(run_id: str) -> dict[str, Any]:
        try:
            run = await async_store.call("get_run", run_id)
            events = await async_store.call("run_events", run_id)
            provider: dict[str, Any] = {}
            if run.get("runtime_profile_id"):
                try:
                    profile = await async_store.call(
                        "get_runtime_profile", str(run["runtime_profile_id"])
                    )
                    config = profile.get("config") if isinstance(profile, dict) else {}
                    provider = {
                        "adapter": profile.get("adapter"),
                        "workspace_url": config.get("workspace_url")
                        if isinstance(config, dict)
                        else None,
                        "external_run_id": run.get("external_run_id"),
                    }
                except KeyError:
                    provider = {"external_run_id": run.get("external_run_id")}
            return {**run, "events": events, "provider": provider}
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.get("/api/runs/{run_id}/events")
    async def run_events(run_id: str, after: int = 0) -> list[dict[str, Any]]:
        """Return run events without requiring the full run detail payload."""
        try:
            await async_store.call("get_run", run_id)
            return await async_store.call("run_events", run_id, after=after)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.get("/api/runs/{run_id}/artifacts")
    async def list_run_artifacts(run_id: str) -> list[dict[str, Any]]:
        """List safe, downloadable artifacts produced for a run."""
        try:
            run = await async_store.call("get_run", run_id)
            root = (
                await _project_path(run["project_id"])
                / ".sdpstudio"
                / "runtime"
                / "run-artifacts"
                / run_id
            )

            def scan() -> list[dict[str, Any]]:
                if not root.exists():
                    return []
                result: list[dict[str, Any]] = []
                for path in sorted(item for item in root.rglob("*") if item.is_file()):
                    relative = path.relative_to(root).as_posix()
                    if relative == "process.json":
                        continue
                    content = path.read_bytes()
                    result.append(
                        {
                            "name": relative,
                            "size_bytes": len(content),
                            "sha256": hashlib.sha256(content).hexdigest(),
                            "download_url": f"/api/runs/{run_id}/artifacts/{relative}",
                        }
                    )
                return result

            return await asyncio.to_thread(scan)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.get("/api/runs/{run_id}/debug-bundle")
    async def debug_bundle(run_id: str) -> FileResponse:
        try:
            run = await async_store.call("get_run", run_id)
            project = await _project_path(run["project_id"])
            artifact_dir = project / ".sdpstudio" / "runtime" / "run-artifacts" / run_id
            artifact_dir.mkdir(parents=True, exist_ok=True)
            bundle = artifact_dir / "debug-bundle.zip"
            events = await async_store.call("run_events", run_id)
            snapshots = await async_store.call("get_node_snapshots", run_id)
            registered: dict[str, str] = {}
            for item in await async_store.call("list_secrets"):
                try:
                    registered[item["name"]] = await async_store.call(
                        "resolve_secret", item["name"]
                    )
                except (KeyError, ValueError):
                    continue
            entries = build_entries(
                run,
                events,
                snapshots,
                artifact_dir=artifact_dir,
                project=project,
                redact_value=_redact_bundle_value,
                registered_secrets=registered,
                redact_registered=_redact_registered_secrets,
            )
            manifest = {
                "schema": 1,
                "files": [
                    {
                        "path": name,
                        "sha256": hashlib.sha256(content).hexdigest(),
                        "size": len(content),
                    }
                    for name, content in sorted(entries.items())
                ],
            }
            entries["manifest.json"] = (
                json.dumps(manifest, indent=2, sort_keys=True) + "\n"
            ).encode("utf-8")
            with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for name, content in sorted(entries.items()):
                    zf.writestr(name, content)
            return FileResponse(
                bundle, media_type="application/zip", filename=f"sdpstudio-debug-{run_id}.zip"
            )
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.get("/api/runs/{run_id}/debug-bundle/preview")
    async def debug_bundle_preview(run_id: str) -> dict[str, Any]:
        """Return the redacted bundle manifest before a user exports it."""
        try:
            run = await async_store.call("get_run", run_id)
            project = await _project_path(run["project_id"])
            artifact_dir = project / ".sdpstudio" / "runtime" / "run-artifacts" / run_id
            events = await async_store.call("run_events", run_id)
            snapshots = await async_store.call("get_node_snapshots", run_id)
            registered: dict[str, str] = {}
            for item in await async_store.call("list_secrets"):
                try:
                    registered[item["name"]] = await async_store.call(
                        "resolve_secret", item["name"]
                    )
                except (KeyError, ValueError):
                    continue
            entries = build_entries(
                run,
                events,
                snapshots,
                artifact_dir=artifact_dir,
                project=project,
                redact_value=_redact_bundle_value,
                registered_secrets=registered,
                redact_registered=_redact_registered_secrets,
            )
            return {
                "schema": 1,
                "redacted": True,
                "files": [
                    {
                        "path": name,
                        "size": len(content),
                        "sha256": hashlib.sha256(content).hexdigest(),
                    }
                    for name, content in sorted(entries.items())
                ],
            }
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/runs/{run_id}/debug-bundle")
    async def export_debug_bundle(run_id: str) -> FileResponse:
        """Mutation-style alias for clients following the normative API."""
        return await debug_bundle(run_id)

    @app.get("/api/runs/{run_id}/artifacts/{artifact_path:path}")
    async def download_run_artifact(run_id: str, artifact_path: str) -> FileResponse:
        try:
            run = await async_store.call("get_run", run_id)
            root = (
                await _project_path(run["project_id"])
                / ".sdpstudio"
                / "runtime"
                / "run-artifacts"
                / run_id
            ).resolve()
            requested = (root / artifact_path).resolve()
            if (
                requested == root
                or root not in requested.parents
                or requested.name == "process.json"
            ):
                raise ValueError("Invalid artifact path")
            if not requested.is_file():
                raise KeyError(f"Artifact not found: {artifact_path}")
            return FileResponse(requested)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/runs/{run_id}/cancel")
    async def cancel_run(run_id: str, request: Request) -> dict[str, Any]:
        _require_role(request, "editor")
        cancelled = await runtime_dispatch.cancel(run_id)
        await async_store.call(
            "append_audit_event",
            _audit_actor(request),
            "run.cancelled",
            "run",
            run_id,
            {"cancelled": cancelled},
        )
        return {"cancelled": cancelled}

    @app.get("/api/runs/{run_id}/kubernetes/status")
    async def kubernetes_run_status(run_id: str) -> dict[str, Any]:
        try:
            return await runtime.kubernetes_status(run_id)
        except (KeyError, ValueError, OSError) as exc:
            raise _http_error(exc) from exc

    @app.get("/api/runs/{run_id}/kubernetes/probe")
    async def kubernetes_run_probe(run_id: str) -> dict[str, Any]:
        try:
            return await runtime.kubernetes_probe(run_id)
        except (KeyError, ValueError, OSError) as exc:
            raise _http_error(exc) from exc

    @app.get("/api/runs/{run_id}/kubernetes/logs")
    async def kubernetes_run_logs(
        run_id: str, tail: int = 200, follow: bool = False
    ) -> dict[str, Any]:
        if tail < 1 or tail > 10_000:
            raise HTTPException(status_code=400, detail="tail must be between 1 and 10000")
        try:
            return await runtime.kubernetes_logs(run_id, tail=tail, follow=follow)
        except (KeyError, ValueError, OSError) as exc:
            raise _http_error(exc) from exc

    @app.get("/api/runs/{run_id}/kubernetes/events")
    async def kubernetes_run_events(run_id: str) -> dict[str, Any]:
        try:
            return await runtime.kubernetes_events(run_id)
        except (KeyError, ValueError, OSError) as exc:
            raise _http_error(exc) from exc

    @app.websocket("/ws/projects/{project_id}")
    async def project_socket(ws: WebSocket, project_id: str) -> None:
        if not _websocket_authorized(ws, auth_token, auth_service):
            await ws.close(code=4401)
            return
        try:
            await async_store.call("get_project", project_id)
        except KeyError:
            await ws.close(code=4404)
            return
        await ws.accept(subprotocol=_websocket_subprotocol(ws))
        request_metrics["active_websockets"] += 1
        socket_role = _websocket_role(ws, auth_service)
        count = await hub.connect(project_id, ws)
        await hub.broadcast(project_id, {"type": "presence", "count": count})
        snapshot = await async_store.call("collaboration_snapshot", project_id)
        if snapshot is not None:
            await ws.send_json({"type": "snapshot", "snapshot": snapshot})
        for event in await async_store.call(
            "collaboration_events", project_id, after=snapshot["seq"] if snapshot else 0
        ):
            await ws.send_json({"type": "replay", "event": event})
        try:
            while True:
                message = await ws.receive_text()
                if message == "ping":
                    await ws.send_json({"type": "pong"})
                    continue
                if len(message) > 2_000_000:
                    await ws.send_json({"type": "error", "code": "COLLAB_MESSAGE_TOO_LARGE"})
                    continue
                try:
                    payload = json.loads(message)
                except json.JSONDecodeError:
                    await ws.send_json({"type": "error", "code": "COLLAB_INVALID_MESSAGE"})
                    continue
                if payload.get("type") == "presence":
                    states = await hub.update_presence(project_id, ws, payload)
                    await hub.broadcast(project_id, {"type": "presence_state", "states": states})
                    continue
                if payload.get("type") == "y_update" and isinstance(payload.get("update"), str):
                    if socket_role == "viewer":
                        await ws.send_json({"type": "error", "code": "COLLAB_READ_ONLY"})
                        continue
                    try:
                        update = _decode_collaboration_update(payload["update"])
                    except ValueError:
                        await ws.send_json({"type": "error", "code": "COLLAB_INVALID_UPDATE"})
                        continue
                    if len(update) > 1_000_000:
                        await ws.send_json({"type": "error", "code": "COLLAB_UPDATE_TOO_LARGE"})
                        continue
                    persisted_update = payload["update"]
                    if merge_enabled:
                        prior_updates: list[bytes] = []
                        if snapshot:
                            prior_updates.extend(
                                _decode_collaboration_update(item["update"])
                                for item in snapshot["document"].get("updates", [])
                                if isinstance(item, dict) and isinstance(item.get("update"), str)
                            )
                        prior_updates.extend(
                            _decode_collaboration_update(item["event"]["update"])
                            for item in await async_store.call(
                                "collaboration_events",
                                project_id,
                                after=snapshot["seq"] if snapshot else 0,
                            )
                            if isinstance(item.get("event"), dict)
                            and isinstance(item["event"].get("update"), str)
                        )
                        try:
                            merged = merge_updates([*prior_updates, update])
                        except (RuntimeError, ValueError):
                            # Keep transport compatibility for updates produced by
                            # another Yjs binding when pycrdt cannot decode them.
                            merged = update
                        persisted_update = (
                            base64.urlsafe_b64encode(merged).decode("ascii").rstrip("=")
                        )
                    event = await async_store.call(
                        "append_collaboration_event",
                        project_id,
                        {
                            "type": "y_update",
                            "update": persisted_update,
                            "client_id": payload.get("client_id"),
                        },
                    )
                    await hub.broadcast(project_id, {"type": "y_update", "event": event})
        except WebSocketDisconnect:
            pass
        finally:
            request_metrics["active_websockets"] = max(0, request_metrics["active_websockets"] - 1)
            count = await hub.disconnect(project_id, ws)
            await hub.broadcast(project_id, {"type": "presence", "count": count})

    @app.websocket("/ws/collab/{project_id}")
    async def collaboration_socket(ws: WebSocket, project_id: str) -> None:
        """Normative collaboration WebSocket alias."""
        await project_socket(ws, project_id)

    @app.get("/api/projects/{project_id}/collaboration/capabilities")
    async def collaboration_capabilities(project_id: str) -> dict[str, Any]:
        await async_store.call("get_project", project_id)
        return {
            "project_id": project_id,
            **COLLABORATION_CAPABILITIES,
            "server_merge": merge_enabled,
        }

    @app.websocket("/ws/runs/{run_id}")
    async def run_socket(ws: WebSocket, run_id: str) -> None:
        if not _websocket_authorized(ws, auth_token, auth_service):
            await ws.close(code=4401)
            return
        await ws.accept(subprotocol=_websocket_subprotocol(ws))
        request_metrics["active_websockets"] += 1
        seq = 0
        try:
            while True:
                events = await async_store.call("run_events", run_id, after=seq)
                for event in events:
                    seq = max(seq, int(event["seq"]))
                    await ws.send_json(_typed_run_event(event))
                run = await async_store.call("get_run", run_id)
                if (
                    run["status"]
                    in {
                        "succeeded",
                        "validation_failed",
                        "failed",
                        "cancelled",
                        "lost",
                    }
                    and not events
                ):
                    await ws.send_json(
                        {
                            "kind": "eof",
                            "type": "run.eof",
                            "status": run["status"],
                            "seq": seq + 1,
                        }
                    )
                    break
                await asyncio.sleep(0.35)
        except (WebSocketDisconnect, KeyError):
            return
        finally:
            request_metrics["active_websockets"] = max(0, request_metrics["active_websockets"] - 1)

    @app.get("/api/projects/{project_id}/history")
    async def history(project_id: str) -> list[dict[str, Any]]:
        try:
            return await async_store.call("list_history", project_id)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/projects/{project_id}/history/checkpoints")
    async def create_history_checkpoint(
        project_id: str, req: HistoryCheckpointRequest, request: Request
    ) -> dict[str, Any]:
        try:
            _require_role(request, "editor")
            return await async_store.call("create_history_checkpoint", project_id, req.name)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.get("/api/projects/{project_id}/history/{snapshot_id}/diff")
    async def history_diff(project_id: str, snapshot_id: str) -> dict[str, Any]:
        try:
            snapshot = await async_store.call("load_history_snapshot", project_id, snapshot_id)
            before = PipelineDocument.model_validate(snapshot["document"])
            current = await async_store.call("load_pipeline", project_id)
            return await asyncio.to_thread(semantic_graph_diff, before, current)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.get("/api/projects/{project_id}/history/{snapshot_id}")
    async def history_snapshot(project_id: str, snapshot_id: str) -> dict[str, Any]:
        try:
            return await async_store.call("load_history_snapshot", project_id, snapshot_id)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/projects/{project_id}/history/{snapshot_id}/restore")
    async def restore_history(
        project_id: str, snapshot_id: str, request: Request
    ) -> dict[str, Any]:
        try:
            _require_role(request, "editor")
            restored = await async_store.call("restore_history", project_id, snapshot_id)
            return restored.model_dump(by_alias=True)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.get("/api/projects/{project_id}/history/{revision_id}/diff")
    async def history_revision_diff(project_id: str, revision_id: str) -> dict[str, Any]:
        """Normative revision_id alias for the legacy snapshot_id history route."""
        return await history_diff(project_id, revision_id)

    @app.get("/api/projects/{project_id}/history/{revision_id}")
    async def history_revision(project_id: str, revision_id: str) -> dict[str, Any]:
        """Normative revision_id alias for the legacy snapshot_id history route."""
        return await history_snapshot(project_id, revision_id)

    @app.post("/api/projects/{project_id}/history/{revision_id}/restore")
    async def restore_revision(
        project_id: str, revision_id: str, request: Request
    ) -> dict[str, Any]:
        """Normative revision_id alias for the legacy snapshot_id history route."""
        return await restore_history(project_id, revision_id, request)

    @app.get("/api/projects/{project_id}/git/status")
    async def git_status(project_id: str) -> dict[str, Any]:
        try:
            return await _git_call("status", project_id)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/projects/{project_id}/git/init")
    async def git_init(project_id: str, request: Request) -> dict[str, Any]:
        try:
            _require_role(request, "editor")
            return await _git_call("init", project_id)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.get("/api/projects/{project_id}/git/diff")
    async def git_diff(project_id: str) -> dict[str, str]:
        try:
            return {"diff": await _git_call("diff", project_id)}
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.get("/api/projects/{project_id}/git/blob-diff")
    async def git_blob_diff(
        project_id: str,
        left: str = Query(..., min_length=1, max_length=200),
        right: str = Query(..., min_length=1, max_length=200),
        path: str = Query(..., min_length=1, max_length=500),
    ) -> dict[str, str]:
        try:
            return {
                "path": path,
                "left": left,
                "right": right,
                "diff": await _git_call("blob_diff", project_id, left, right, path),
            }
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.get("/api/projects/{project_id}/git/graph-diff")
    async def git_graph_diff(
        project_id: str,
        left: str = Query(..., min_length=1, max_length=200),
        right: str = Query(..., min_length=1, max_length=200),
        path: str = Query(".sdpstudio/pipelines/main.sdpstudio.yaml", min_length=1, max_length=500),
    ) -> dict[str, Any]:
        try:
            left_source, right_source = await asyncio.gather(
                _git_call("read_blob", project_id, left, path),
                _git_call("read_blob", project_id, right, path),
            )
            before = PipelineDocument.model_validate(yaml.safe_load(left_source))
            after = PipelineDocument.model_validate(yaml.safe_load(right_source))
            return {
                "path": path,
                "left": left,
                "right": right,
                "diff": semantic_graph_diff(before, after),
            }
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/projects/{project_id}/git/commit")
    async def git_commit(project_id: str, req: CommitRequest, request: Request) -> dict[str, Any]:
        try:
            _require_role(request, "editor")
            return await _git_call("commit", project_id, req.message)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.get("/api/projects/{project_id}/git/remotes")
    async def git_remotes(project_id: str) -> dict[str, str]:
        try:
            return await _git_call("remotes", project_id)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/projects/{project_id}/git/remotes")
    async def git_set_remote(
        project_id: str, req: RemoteRequest, request: Request
    ) -> dict[str, str]:
        try:
            _require_role(request, "editor")
            return await _git_call("set_remote", project_id, req.name, req.url)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/projects/{project_id}/git/fetch")
    async def git_fetch(project_id: str, req: GitSyncRequest, request: Request) -> dict[str, Any]:
        try:
            _require_role(request, "editor")
            return await _git_call("fetch", project_id, req.remote)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/projects/{project_id}/git/pull")
    async def git_pull(project_id: str, req: GitSyncRequest, request: Request) -> dict[str, Any]:
        try:
            _require_role(request, "editor")
            return await _git_call("pull", project_id, req.remote, req.branch)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/projects/{project_id}/git/push")
    async def git_push(project_id: str, req: GitSyncRequest, request: Request) -> dict[str, Any]:
        try:
            _require_role(request, "editor")
            result = await _git_call("push", project_id, req.remote, req.branch)
            await async_store.call(
                "append_audit_event",
                _audit_actor(request),
                "git.push",
                "project",
                project_id,
                {"remote": req.remote, "branch": req.branch},
            )
            return result
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/projects/{project_id}/git/review")
    async def git_review(project_id: str, req: ReviewRequest, request: Request) -> dict[str, Any]:
        try:
            _require_role(request, "editor")
            remotes = await _git_call("remotes", project_id)
            if req.remote not in remotes:
                raise ValueError(f"Git remote {req.remote!r} is not configured")
            selected_provider = req.provider
            if selected_provider == "auto":
                from .provider_reviews import parse_remote

                selected_provider = parse_remote(remotes[req.remote]).provider or ""
            token = await async_store.call("resolve_secret", f"provider.{selected_provider}.token")
            return await asyncio.to_thread(
                create_review,
                remotes[req.remote],
                provider=req.provider,
                title=req.title,
                body=req.body,
                head=req.head,
                base=req.base,
                token=token,
            )
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.get("/api/projects/{project_id}/git/reviews")
    async def git_reviews(
        project_id: str, remote: str = "origin", provider: str = "auto"
    ) -> list[dict[str, Any]]:
        try:
            remotes = await _git_call("remotes", project_id)
            if remote not in remotes:
                raise ValueError(f"Git remote {remote!r} is not configured")
            from .provider_reviews import parse_remote

            selected_provider = (
                provider if provider != "auto" else (parse_remote(remotes[remote]).provider or "")
            )
            token = await async_store.call("resolve_secret", f"provider.{selected_provider}.token")
            return await asyncio.to_thread(
                list_provider_reviews, remotes[remote], provider=provider, token=token
            )
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.get("/api/projects/{project_id}/reviews")
    async def reviews(
        project_id: str, remote: str = "origin", provider: str = "auto"
    ) -> list[dict[str, Any]]:
        """Normative reviews alias for the legacy Git-scoped route."""
        return await git_reviews(project_id, remote=remote, provider=provider)

    @app.get("/api/projects/{project_id}/git/repository")
    async def git_repository(
        project_id: str, remote: str = "origin", provider: str = "auto"
    ) -> dict[str, Any]:
        try:
            remotes = await _git_call("remotes", project_id)
            if remote not in remotes:
                raise ValueError(f"Git remote {remote!r} is not configured")
            from .provider_reviews import parse_remote

            selected_provider = (
                provider if provider != "auto" else (parse_remote(remotes[remote]).provider or "")
            )
            token = await async_store.call("resolve_secret", f"provider.{selected_provider}.token")
            return await asyncio.to_thread(
                provider_repository, remotes[remote], provider=provider, token=token
            )
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.get("/api/projects/{project_id}/git/branches")
    async def git_branches(project_id: str) -> dict[str, Any]:
        try:
            return await _git_call("branches", project_id)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.get("/api/projects/{project_id}/git/log")
    async def git_log(project_id: str, limit: int = 50) -> list[dict[str, str]]:
        try:
            return await _git_call("log", project_id, limit)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.get("/api/projects/{project_id}/git/tags")
    async def git_tags(project_id: str) -> list[str]:
        try:
            return await _git_call("tags", project_id)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/projects/{project_id}/git/tags")
    async def git_create_tag(project_id: str, req: TagRequest, request: Request) -> list[str]:
        try:
            _require_role(request, "editor")
            return await _git_call("create_tag", project_id, req.name, req.message)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.get("/api/projects/{project_id}/git/stash")
    async def git_stash_list(project_id: str) -> list[str]:
        try:
            result = await _git_call("stash", project_id, "list")
            return result if isinstance(result, list) else []
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/projects/{project_id}/git/stash")
    async def git_stash_action(
        project_id: str, req: StashRequest, request: Request
    ) -> dict[str, Any] | list[str]:
        try:
            _require_role(request, "editor")
            return await _git_call("stash", project_id, req.action, req.message)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.get("/api/projects/{project_id}/git/conflicts")
    async def git_conflicts(project_id: str) -> list[str]:
        try:
            return await _git_call("conflicts", project_id)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.get("/api/projects/{project_id}/git/conflicts/{path:path}")
    async def git_conflict_versions(project_id: str, path: str) -> dict[str, str]:
        try:
            return await _git_call("conflict_versions", project_id, path)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/projects/{project_id}/git/conflicts/resolve")
    async def resolve_git_conflict(
        project_id: str, req: ConflictResolutionRequest, request: Request
    ) -> dict[str, Any]:
        try:
            _require_role(request, "editor")
            return await _git_call("resolve_conflict", project_id, req.path, req.strategy)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/projects/{project_id}/git/stage")
    async def git_stage(
        project_id: str, request: Request, req: GitPathsRequest | None = None
    ) -> dict[str, Any]:
        try:
            _require_role(request, "editor")
            return await _git_call("stage", project_id, req.paths if req else None)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/projects/{project_id}/git/unstage")
    async def git_unstage(
        project_id: str, request: Request, req: GitPathsRequest | None = None
    ) -> dict[str, Any]:
        try:
            _require_role(request, "editor")
            return await _git_call("unstage", project_id, req.paths if req else None)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/projects/{project_id}/git/branches")
    async def git_branch(project_id: str, req: BranchRequest, request: Request) -> dict[str, Any]:
        try:
            _require_role(request, "editor")
            return await _git_call("create_branch", project_id, req.name)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/projects/{project_id}/git/branches/switch")
    async def git_switch_branch(
        project_id: str, req: BranchRequest, request: Request
    ) -> dict[str, Any]:
        try:
            _require_role(request, "editor")
            return await _git_call("switch_branch", project_id, req.name)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/projects/{project_id}/git/checkout")
    async def git_checkout(project_id: str, req: BranchRequest, request: Request) -> dict[str, Any]:
        """Normative checkout alias for branch switching."""
        return await git_switch_branch(project_id, req, request)

    @app.api_route("/api/projects/{project_id}/git/branches", methods=["DELETE"])
    async def git_delete_branch(
        project_id: str, req: BranchDeleteRequest, request: Request
    ) -> dict[str, Any]:
        try:
            _require_role(request, "editor")
            return await _git_call("delete_branch", project_id, req.name, force=req.force)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.get("/api/projects/{project_id}/debug/plan")
    async def debug_plan(project_id: str) -> dict[str, Any]:
        try:
            document = await async_store.call("load_pipeline", project_id)
            runs = await async_store.call("list_runs", project_id)
            for run in runs:
                run_id = str(run.get("id", ""))
                artifact = (
                    Path(str(await _project_path(project_id)))
                    / ".sdpstudio"
                    / "runtime"
                    / "run-artifacts"
                    / run_id
                    / "plan.json"
                )
                if artifact.is_file():
                    payload = json.loads(artifact.read_text(encoding="utf-8"))
                    if isinstance(payload, dict):
                        payload.setdefault("source", "captured_run_artifact")
                        payload.setdefault("run_id", run_id)
                        return payload
            return await asyncio.to_thread(static_debug_plan, document)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/debug/plan/parse")
    async def parse_plan(req: ExplainPlanRequest) -> dict[str, Any]:
        parsed = parse_explain_plan(req.explain)
        if req.before is not None:
            parsed["diff"] = plan_diff(req.before, parsed)
        return parsed

    @app.get("/api/projects/{project_id}/debug/row-trace/{node_id}")
    async def debug_row_trace(project_id: str, node_id: str) -> dict[str, Any]:
        try:
            document = await async_store.call("load_pipeline", project_id)
            return await asyncio.to_thread(row_trace, document, node_id)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/projects/{project_id}/debug/row-trace/execute")
    async def execute_debug_row_trace(project_id: str, req: RowTraceRequest) -> dict[str, Any]:
        try:
            document = await async_store.call("load_pipeline", project_id)
            rows = req.rows
            execution_backed = False
            trace_instrumentation = None
            if not rows:
                preview = await runtime.preview(
                    project_id, req.node_id, req.limit, include_trace=True
                )
                if not preview.get("ok", True):
                    return preview
                trace_rows = preview.get("trace_rows", preview.get("rows", []))
                rows = [row for row in trace_rows if isinstance(row, dict)]
                trace_instrumentation = preview.get("trace_instrumentation")
                execution_backed = True
            try:
                if os.environ.get("SDPSTUDIO_ROW_TRACE_SPARK", "0") != "1":
                    raise RuntimeError("Spark Row Trace is opt-in")
                result = await asyncio.to_thread(
                    execute_row_trace_spark,
                    document,
                    req.node_id,
                    rows,
                    max_rows=req.limit,
                    rows_by_source=req.rows_by_source,
                )
            except (ImportError, RuntimeError, ValueError):
                result = await asyncio.to_thread(
                    execute_row_trace,
                    document,
                    req.node_id,
                    rows,
                    max_rows=req.limit,
                    rows_by_source=req.rows_by_source,
                )
            result["execution_backed"] = execution_backed
            result["provenance"] = (
                "runtime_preview_rows" if execution_backed else "caller_supplied_rows"
            )
            result["trace_mode"] = "execution" if execution_backed else "sample"
            if execution_backed:
                result["runtime_trace_ids"] = [
                    row.get("__sdpstudio_trace_id")
                    for row in rows
                    if row.get("__sdpstudio_trace_id") is not None
                ][: req.limit]
            if trace_instrumentation:
                result["trace_instrumentation"] = trace_instrumentation
            return result
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/projects/{project_id}/quality/evaluate")
    async def evaluate_project_quality(
        project_id: str, req: QualityEvaluateRequest
    ) -> dict[str, Any]:
        try:
            document = await async_store.call("load_pipeline", project_id)
            node = next((item for item in document.nodes if item.id == req.node_id), None)
            if node is None:
                raise KeyError(req.node_id)
            if not node.type.startswith("quality."):
                raise ValueError("Node is not a quality operator")
            return await asyncio.to_thread(
                evaluate_quality, node.type, node.config, req.rows[: req.limit]
            )
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/projects/{project_id}/quality/suite/evaluate")
    async def evaluate_project_quality_suite(
        project_id: str, req: QualitySuiteEvaluateRequest
    ) -> dict[str, Any]:
        """Execute the project's versioned quality suite against bounded rows.

        The suite remains data-source agnostic: preview, post-run, and scheduled
        callers provide the bounded snapshot for each check, while the core suite
        loader owns validation and deterministic evaluation semantics.
        """
        suite_path = store.project_path(project_id) / ".sdpstudio" / "tests" / "quality.yaml"
        try:
            rows = {
                str(check_id): values[: req.limit] for check_id, values in req.rows_by_check.items()
            }
            if req.automatic:
                # Automatic preview/post-run/scheduled execution resolves each
                # suite check from its declared pipeline node. Callers may still
                # provide bounded snapshots for checks that have no node binding.
                for check in load_quality_suite(suite_path):
                    if req.mode is not None and check["mode"] != req.mode:
                        continue
                    node_id = check["config"].get("nodeId")
                    if isinstance(node_id, str) and node_id:
                        preview = await runtime_dispatch.preview(project_id, node_id, req.limit)
                        rows[check["id"]] = list(preview.get("rows", []))[: req.limit]
            return await asyncio.to_thread(execute_quality_suite, suite_path, rows, mode=req.mode)
        except (QualitySuiteError, OSError, ValueError) as exc:
            raise _http_error(exc) from exc

    @app.post("/api/debug/event-log/analyze")
    async def analyze_event_log(req: EventLogRequest) -> dict[str, Any]:
        return summarize_spark_events(req.events)

    @app.post("/api/debug/streaming/analyze")
    async def analyze_streaming_events(req: EventLogRequest) -> dict[str, Any]:
        return summarize_streaming_events(req.events)

    @app.post("/api/debug/redaction-preview")
    async def redaction_preview(req: RedactionPreviewRequest, request: Request) -> dict[str, Any]:
        try:
            _require_role(request, "editor")
            registered: dict[str, str] = {}
            for item in await async_store.call("list_secrets"):
                try:
                    registered[item["name"]] = await async_store.call(
                        "resolve_secret", item["name"]
                    )
                except (KeyError, ValueError):
                    continue
            payload, matched = _redact_registered_secrets(req.payload, registered)
            return {
                "payload": _redact_bundle_value(payload),
                "matched_secret_names": sorted(matched),
                "changed": bool(matched),
            }
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/debug/diagnostics")
    async def diagnostics(req: DiagnosticRequest) -> dict[str, Any]:
        return {
            "findings": diagnose(
                error_class=req.error_class, message=req.message, context=req.context
            )
        }

    @app.post("/api/projects/{project_id}/debug/compare-runs")
    async def compare_runs(project_id: str, req: CompareRunsRequest) -> dict[str, Any]:
        try:
            left, right = await asyncio.gather(
                async_store.call("get_run", req.left_run_id),
                async_store.call("get_run", req.right_run_id),
            )
            if left["project_id"] != project_id or right["project_id"] != project_id:
                raise ValueError("Runs must belong to this project")

            ldur, rdur = duration_seconds(left), duration_seconds(right)
            graph_diff = None
            left_snapshot_data: dict[str, Any] = {}
            right_snapshot_data: dict[str, Any] = {}
            project_path = await _project_path(project_id)
            left_snapshot = (
                project_path
                / ".sdpstudio"
                / "runtime"
                / "run-artifacts"
                / req.left_run_id
                / "run-snapshot.json"
            )
            right_snapshot = (
                project_path
                / ".sdpstudio"
                / "runtime"
                / "run-artifacts"
                / req.right_run_id
                / "run-snapshot.json"
            )
            if left_snapshot.exists() and right_snapshot.exists():
                a = json.loads(left_snapshot.read_text(encoding="utf-8"))
                b = json.loads(right_snapshot.read_text(encoding="utf-8"))
                left_snapshot_data, right_snapshot_data = a, b
                graph_diff = semantic_graph_diff(
                    PipelineDocument.model_validate(a["pipeline"]),
                    PipelineDocument.model_validate(b["pipeline"]),
                )
            left_events, right_events = await asyncio.gather(
                async_store.call("run_events", req.left_run_id),
                async_store.call("run_events", req.right_run_id),
            )
            left_problems = [event for event in left_events if event.get("kind") == "problem"]
            right_problems = [event for event in right_events if event.get("kind") == "problem"]
            left_profile = left_snapshot_data.get("runtime_profile", {})
            right_profile = right_snapshot_data.get("runtime_profile", {})
            left_capabilities = left_snapshot_data.get("runtime_capabilities", {})
            right_capabilities = right_snapshot_data.get("runtime_capabilities", {})

            def event_summary(run_id: str) -> dict[str, Any] | None:
                path = (
                    project_path
                    / ".sdpstudio"
                    / "runtime"
                    / "run-artifacts"
                    / run_id
                    / "event-summary.json"
                )
                if not path.exists():
                    return None
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    return payload if isinstance(payload, dict) else None
                except (OSError, json.JSONDecodeError):
                    return None

            left_metrics, right_metrics = (
                event_summary(req.left_run_id),
                event_summary(req.right_run_id),
            )
            metric_deltas = stage_metric_deltas(left_metrics, right_metrics)

            def plan_artifact(run_id: str) -> dict[str, Any] | None:
                path = (
                    project_path / ".sdpstudio" / "runtime" / "run-artifacts" / run_id / "plan.json"
                )
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    return None
                return payload if isinstance(payload, dict) else None

            left_plan, right_plan = plan_artifact(req.left_run_id), plan_artifact(req.right_run_id)

            def compare_plans(
                before: dict[str, Any] | None, after: dict[str, Any] | None
            ) -> dict[str, Any]:
                if not before or not after:
                    return {"available": False, "reason": "plan artifact missing"}
                left_nodes = {str(item.get("node_id")): item for item in before.get("plans", [])}
                right_nodes = {str(item.get("node_id")): item for item in after.get("plans", [])}
                diffs = []
                for node_id in sorted(set(left_nodes) | set(right_nodes)):
                    left_parsed = left_nodes.get(node_id, {}).get("parsed")
                    right_parsed = right_nodes.get(node_id, {}).get("parsed")
                    if not isinstance(left_parsed, dict) or not isinstance(right_parsed, dict):
                        diffs.append({"node_id": node_id, "available": False})
                    else:
                        diffs.append(
                            {
                                "node_id": node_id,
                                "available": True,
                                "diff": plan_diff(left_parsed, right_parsed),
                            }
                        )
                return {"available": True, "nodes": diffs}

            plan_comparison = compare_plans(left_plan, right_plan)
            left_snapshot_items, right_snapshot_items = await asyncio.gather(
                async_store.call("get_node_snapshots", req.left_run_id),
                async_store.call("get_node_snapshots", req.right_run_id),
            )
            schema_nodes, quality_nodes = node_diffs(left_snapshot_items, right_snapshot_items)
            left_source = left_snapshot_data.get("generated_code")
            right_source = right_snapshot_data.get("generated_code")
            source_diff = None
            if left_source is not None and right_source is not None:
                left_text = (
                    left_source
                    if isinstance(left_source, str)
                    else json.dumps(left_source, sort_keys=True, indent=2)
                )
                right_text = (
                    right_source
                    if isinstance(right_source, str)
                    else json.dumps(right_source, sort_keys=True, indent=2)
                )
                source_diff = "".join(
                    difflib.unified_diff(
                        left_text.splitlines(keepends=True),
                        right_text.splitlines(keepends=True),
                        fromfile="left/generated",
                        tofile="right/generated",
                    )
                )[:1_000_000]
            return {
                "left": left,
                "right": right,
                "code_changed": left.get("code_hash") != right.get("code_hash"),
                "duration_seconds": {
                    "left": ldur,
                    "right": rdur,
                    "delta": None if ldur is None or rdur is None else rdur - ldur,
                },
                "status_changed": left.get("status") != right.get("status"),
                "mode_changed": left.get("mode") != right.get("mode"),
                "graph_diff": graph_diff,
                "source_diff": {
                    "left_code_hash": left.get("code_hash"),
                    "right_code_hash": right.get("code_hash"),
                    "generated_source_available": source_diff is not None,
                    "unified_diff": source_diff,
                },
                "runtime_diff": {
                    "profile_changed": left_profile != right_profile,
                    "capabilities_changed": left_capabilities != right_capabilities,
                    "left_profile": left_profile,
                    "right_profile": right_profile,
                },
                "node_metric_deltas": metric_deltas,
                "schema_diffs": {
                    "available": bool(schema_nodes),
                    "nodes": schema_nodes,
                    "reason": None
                    if schema_nodes
                    else "No persisted schema snapshots were captured for one or both runs.",
                },
                "quality_diffs": {
                    "available": any(item["available"] for item in quality_nodes.values()),
                    "nodes": quality_nodes,
                    "reason": None
                    if any(item["available"] for item in quality_nodes.values())
                    else "No persisted profile metrics were captured for one or both runs.",
                },
                "problems_delta": {
                    "left_count": len(left_problems),
                    "right_count": len(right_problems),
                    "added_messages": sorted(
                        {str(item.get("message", "")) for item in right_problems}
                        - {str(item.get("message", "")) for item in left_problems}
                    ),
                    "removed_messages": sorted(
                        {str(item.get("message", "")) for item in left_problems}
                        - {str(item.get("message", "")) for item in right_problems}
                    ),
                },
                "plan_diff_available": bool(
                    (
                        project_path
                        / ".sdpstudio"
                        / "runtime"
                        / "run-artifacts"
                        / req.left_run_id
                        / "plan.json"
                    ).exists()
                    and (
                        project_path
                        / ".sdpstudio"
                        / "runtime"
                        / "run-artifacts"
                        / req.right_run_id
                        / "plan.json"
                    ).exists()
                ),
                "plan_diff": plan_comparison,
            }
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.post("/api/runs/compare")
    async def compare_runs_global(req: CompareRunsRequest) -> dict[str, Any]:
        """Compare two runs through the normative global endpoint."""
        try:
            left = await async_store.call("get_run", req.left_run_id)
            return await compare_runs(str(left["project_id"]), req)
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.get("/api/projects/{project_id}/debug/schema-timeline")
    async def debug_schema_timeline(project_id: str, request: Request) -> dict[str, Any]:
        try:
            _require_role(request, "editor")
            runs = await async_store.call("list_runs", project_id)
            snapshots = await asyncio.gather(
                *(async_store.call("get_node_snapshots", run["id"]) for run in runs)
            )
            timeline = schema_timeline(
                runs,
                {str(run["id"]): items for run, items in zip(runs, snapshots, strict=True)},
            )
            return {"project_id": project_id, "timeline": timeline}
        except Exception as exc:
            raise _http_error(exc) from exc

    @app.get("/")
    async def index() -> FileResponse:
        canonical = react_root / "react-index.html"
        return FileResponse(canonical if canonical.exists() else web_root / "index.html")

    def openapi_with_versioned_aliases() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        aliases = {
            f"/api/v1{path[4:]}": operation
            for path, operation in schema["paths"].items()
            if path.startswith("/api/")
        }
        schema["paths"].update(aliases)
        app.openapi_schema = schema
        return schema

    app.openapi = cast(Any, openapi_with_versioned_aliases)  # type: ignore[method-assign]

    return app
