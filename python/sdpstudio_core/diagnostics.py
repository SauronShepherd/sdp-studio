from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import yaml


@dataclass(frozen=True)
class DiagnosticRule:
    id: str
    message: str
    error_class: str | None = None
    log_pattern: str | None = None
    checks: tuple[str, ...] = ()
    severity: str = "error"
    remediation: str | None = None


DEFAULT_RULES_YAML = """
- id: spark.analysis.unresolved-column
  match:
    errorClass: "UNRESOLVED_COLUMN.*"
  message: "A referenced column cannot be resolved."
  checks:
    - "Compare the node input schema with the expression."
  remediation: "Check spelling, aliases, and the upstream schema."
- id: spark.analysis.unresolved-table
  match:
    errorClass: "TABLE_OR_VIEW_NOT_FOUND.*"
  message: "The referenced table or view cannot be found."
  checks:
    - "Verify catalog, namespace, and table permissions."
  remediation: "Check the runtime catalog and source configuration."
- id: spark.streaming-checkpoint
  match:
    message: "(?i).*checkpoint.*"
  message: "The streaming checkpoint configuration needs attention."
  checks:
    - "Confirm the checkpoint path is durable and unique for this query."
  remediation: "Use a writable, shared checkpoint path and avoid reusing it across incompatible graphs."
- id: spark.kubernetes-image-pull
  match:
    message: "(?i).*(imagepullbackoff|errimagepull).*"
  message: "Kubernetes cannot pull the configured Spark image."
  checks:
    - "Inspect image name, registry credentials, and namespace pull-secret bindings."
  remediation: "Verify the image exists and configure an allowlisted image pull secret."
- id: spark.analysis.type-mismatch
  match:
    errorClass: "DATATYPE_MISMATCH.*"
  message: "An expression has an incompatible data type."
  checks:
    - "Compare expression operands with the input schema types."
  remediation: "Cast the value explicitly or select an operator with compatible types."
- id: spark.analysis.ambiguous-reference
  match:
    errorClass: "AMBIGUOUS_REFERENCE.*"
  message: "A column reference is ambiguous after a join or projection."
  checks:
    - "Inspect duplicate column names from upstream inputs."
  remediation: "Qualify the reference or rename the duplicate columns."
- id: sdp.mode-mismatch
  match:
    message: "(?i).*(streaming.*batch|batch.*streaming|mode mismatch).*"
  message: "A streaming and batch boundary is incompatible."
  checks:
    - "Verify the source mode and downstream operator contract."
  remediation: "Use a compatible streaming operator or materialize the boundary."
- id: sdp.unsupported-action
  match:
    message: "(?i).*(unsupported.*(action|operation)|not supported).*"
  message: "The runtime does not support the requested pipeline action."
  checks:
    - "Check runtime capabilities and the selected operator contract."
  remediation: "Choose a supported action or switch to a compatible runtime."
- id: spark.session-mutation
  match:
    message: '(?i).*(session.*(mutat|changed)|spark[.]conf[.]set).*'
  message: "Pipeline code mutated shared Spark session state."
  checks:
    - "Locate session configuration changes in user-owned code."
  remediation: "Move settings into the runtime profile or an approved configuration boundary."
- id: spark.executor-oom
  match:
    errorClass: "RESOURCE_EXHAUSTED.*|OUT_OF_MEMORY.*"
    message: "(?i).*(out.of.memory|java heap|executor.*oom).*"
  message: "A Spark executor ran out of memory."
  checks:
    - "Inspect skew, partition sizes, and wide transformations."
  remediation: "Reduce partition pressure or increase executor memory within policy."
- id: spark.connector-missing
  match:
    message: "(?i).*(classnotfound|no suitable driver|connector.*(missing|not found)).*"
  message: "A required Spark connector or provider class is unavailable."
  checks:
    - "Verify runtime libraries and connector versions."
  remediation: "Install the approved connector or select a runtime profile that provides it."
- id: kubernetes.rbac-denied
  match:
    message: "(?i).*(forbidden|rbac|cannot.*(get|list|watch).*pods).*"
  message: "Kubernetes RBAC denied a required runtime operation."
  checks:
    - "Run the configured service-account access probe in the target namespace."
  remediation: "Grant only the required allowlisted permissions to the runtime service account."
"""


def load_rules(source: str = DEFAULT_RULES_YAML) -> tuple[DiagnosticRule, ...]:
    payload = yaml.safe_load(source) or []
    if not isinstance(payload, list):
        raise ValueError("Diagnostic rules must be a YAML list")
    rules: list[DiagnosticRule] = []
    for item in payload:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ValueError("Each diagnostic rule requires an id")
        match = item.get("match") or {}
        if not isinstance(match, dict):
            raise ValueError(f"Diagnostic rule {item['id']!r} has invalid match")
        checks = item.get("checks") or []
        if not isinstance(checks, list) or not all(isinstance(check, str) for check in checks):
            raise ValueError(f"Diagnostic rule {item['id']!r} has invalid checks")
        error_class = match.get("errorClass")
        log_pattern = match.get("message")
        for pattern in (error_class, log_pattern):
            if pattern is not None:
                if not isinstance(pattern, str) or len(pattern) > 500:
                    raise ValueError(f"Diagnostic rule {item['id']!r} has an unsafe pattern")
                re.compile(pattern)
        rules.append(
            DiagnosticRule(
                id=item["id"],
                message=str(item.get("message") or item["id"]),
                error_class=error_class,
                log_pattern=log_pattern,
                checks=tuple(checks),
                severity=str(item.get("severity") or "error"),
                remediation=item.get("remediation"),
            )
        )
    return tuple(rules)


def diagnose(
    *,
    error_class: str | None = None,
    message: str = "",
    rules: tuple[DiagnosticRule, ...] | None = None,
    context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    bounded_message = message[:10_000]
    bounded_class = (error_class or "")[:500]
    findings: list[dict[str, Any]] = []
    for rule in rules or load_rules():
        class_match = (
            rule.error_class is None or re.search(rule.error_class, bounded_class) is not None
        )
        message_match = (
            rule.log_pattern is None or re.search(rule.log_pattern, bounded_message) is not None
        )
        if class_match and message_match:
            findings.append(
                {
                    "id": rule.id,
                    "code": f"SDPS-DIAG-{rule.id.upper().replace('.', '-')}",
                    "severity": rule.severity,
                    "message": rule.message,
                    "probable_cause": rule.message,
                    "line": (context or {}).get("line"),
                    "doc_link": (context or {}).get("doc_link"),
                    "checks": list(rule.checks),
                    "remediation": rule.remediation,
                    "context": context or {},
                }
            )
    return findings
