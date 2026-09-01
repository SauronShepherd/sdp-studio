import json
import logging

from sdpstudio_server.observability import (
    StructuredJsonFormatter,
    finish_span,
    instrument_fastapi,
    request_id_context,
    run_id_context,
    start_request_span,
)


def test_structured_logs_are_json_and_redact_secrets():
    request_token = request_id_context.set("req-1")
    run_token = run_id_context.set("run-1")
    try:
        record = logging.LogRecord(
            "test", logging.INFO, __file__, 1, "Bearer secret-value", (), None
        )
        payload = json.loads(StructuredJsonFormatter().format(record))
    finally:
        request_id_context.reset(request_token)
        run_id_context.reset(run_token)
    assert payload["message"] == "Bearer [REDACTED]"
    assert payload["request_id"] == "req-1"
    assert payload["run_id"] == "run-1"


def test_structured_logs_preserve_safe_fields_and_redact_nested_values():
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "operation", (), None)
    record.operation = "preview"
    record.duration_ms = 12.5
    record.details = {"rows": 3, "api_key": "hidden", "status": "ok"}
    payload = json.loads(StructuredJsonFormatter().format(record))
    assert payload["fields"]["operation"] == "preview"
    assert payload["fields"]["duration_ms"] == 12.5
    assert payload["fields"]["details"]["api_key"] == "[REDACTED]"
    assert payload["fields"]["details"]["rows"] == 3


def test_otel_boundary_is_opt_in_and_safe_without_optional_dependency(monkeypatch):
    monkeypatch.delenv("SDPSTUDIO_OTEL", raising=False)
    span = start_request_span("request", request_id="req", method="GET", path="/health")
    assert span is None
    finish_span(span, status_code=200, duration_seconds=0.001)
    assert instrument_fastapi(object()) is False
