"""Dependency-free structured logging and metric context helpers."""

from __future__ import annotations

import json
import logging
import os
import re
from contextvars import ContextVar
from typing import Any

request_id_context: ContextVar[str] = ContextVar("sdpstudio_request_id", default="")
run_id_context: ContextVar[str] = ContextVar("sdpstudio_run_id", default="")
_SECRET = re.compile(r"(?i)(bearer\s+|(?:token|password|secret|api[_-]?key)\s*[=:]\s*)[^\s,;]+")
_SENSITIVE_KEY = re.compile(r"(?i)(token|password|secret|api[_-]?key|private[_-]?key)")
_STANDARD_RECORD_FIELDS = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__)
_otel_configured = False
_otel_app_instrumented = False


def configure_otel() -> bool:
    """Install an SDK provider when explicitly enabled by the deployment.

    The console exporter is opt-in so local runs never emit telemetry or need
    optional OpenTelemetry packages. Deployments can replace the provider via
    their normal OpenTelemetry auto-configuration before starting the server.
    """
    global _otel_configured
    if _otel_configured or os.environ.get("SDPSTUDIO_OTEL", "0") != "1":
        return _otel_configured
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    except ImportError:
        return False
    if not isinstance(trace.get_tracer_provider(), TracerProvider):
        provider = TracerProvider()
        if os.environ.get("SDPSTUDIO_OTEL_CONSOLE", "0") == "1":
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        trace.set_tracer_provider(provider)
    _otel_configured = True
    return True


def instrument_fastapi(app: Any) -> bool:
    """Enable standard HTTP spans when optional OpenTelemetry is configured."""
    global _otel_app_instrumented
    if _otel_app_instrumented or os.environ.get("SDPSTUDIO_OTEL", "0") != "1":
        return _otel_app_instrumented
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
    except (ImportError, RuntimeError, ValueError):
        return False
    _otel_app_instrumented = True
    return True


def start_request_span(name: str, *, request_id: str, method: str, path: str) -> Any:
    """Start an optional OpenTelemetry span without making it a core dependency."""
    if os.environ.get("SDPSTUDIO_OTEL", "0") != "1":
        return None
    try:
        from opentelemetry import trace

        span = trace.get_tracer("sdpstudio.server").start_span(name)
        span.set_attribute("http.request.method", method)
        span.set_attribute("url.path", path)
        span.set_attribute("sdpstudio.request_id", request_id)
        return span
    except (ImportError, RuntimeError):
        return None


def finish_span(span: Any, *, status_code: int, duration_seconds: float) -> None:
    if span is None:
        return
    try:
        span.set_attribute("http.response.status_code", status_code)
        span.set_attribute("sdpstudio.duration_seconds", duration_seconds)
        span.end()
    except (AttributeError, RuntimeError):
        return


def _safe_extra(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if _SENSITIVE_KEY.search(str(key)) else _safe_extra(item)
            for key, item in value.items()
        }
    if isinstance(value, list | tuple):
        return [_safe_extra(item) for item in value]
    if isinstance(value, str):
        return _SECRET.sub(r"\1[REDACTED]", value)
    if isinstance(value, int | float | bool) or value is None:
        return value
    return str(value)


class StructuredJsonFormatter(logging.Formatter):
    """Emit stable JSON records without serializing secret-bearing fields."""

    def format(self, record: logging.LogRecord) -> str:
        message = _SECRET.sub(r"\1[REDACTED]", record.getMessage())
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": message,
        }
        request_id = request_id_context.get()
        run_id = run_id_context.get()
        if request_id:
            payload["request_id"] = request_id
        if run_id:
            payload["run_id"] = run_id
        extras = {
            key: _safe_extra(value)
            for key, value in record.__dict__.items()
            if key not in _STANDARD_RECORD_FIELDS and not key.startswith("_")
        }
        if extras:
            payload["fields"] = extras
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def configure_structured_logging() -> None:
    """Install JSON formatting only when explicitly requested by deployment."""
    if __import__("os").environ.get("SDPSTUDIO_JSON_LOGS", "0") != "1":
        return
    handler = logging.StreamHandler()
    handler.setFormatter(StructuredJsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
