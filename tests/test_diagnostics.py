from pathlib import Path

import pytest
import yaml
from sdpstudio_core.diagnostics import diagnose, load_rules


def test_diagnostics_match_error_class_and_include_actionable_checks():
    findings = diagnose(error_class="UNRESOLVED_COLUMN.WITH_SUGGESTION", message="missing col")
    assert findings[0]["id"] == "spark.analysis.unresolved-column"
    assert findings[0]["checks"]
    assert findings[0]["remediation"]


def test_diagnostics_match_bounded_log_messages():
    assert diagnose(message="pod is in ImagePullBackOff")
    assert not diagnose(message="x" * 10_001 + "checkpoint")


def test_diagnostic_findings_include_problem_navigation_metadata():
    findings = diagnose(
        message="checkpoint failure",
        context={"line": 12, "doc_link": "docs/guides/README.md"},
    )
    finding = next(item for item in findings if item["id"] == "spark.streaming-checkpoint")
    assert finding["line"] == 12
    assert finding["doc_link"].endswith("guides/README.md")
    assert finding["probable_cause"]


def test_diagnostic_rules_reject_invalid_or_oversized_regex():
    with pytest.raises(ValueError):
        load_rules("- id: bad\n  match: nope\n")
    with pytest.raises((ValueError, __import__("re").error)):
        load_rules("- id: bad\n  match:\n    message: '['\n")


def test_shipped_diagnostic_pack_matches_runtime_defaults():
    shipped = yaml.safe_load(Path("docs/diagnostics/rules.yaml").read_text(encoding="utf-8"))
    assert [item["id"] for item in shipped] == [rule.id for rule in load_rules()]


def test_diagnostic_pack_covers_required_runtime_failure_categories():
    cases = [
        ("DATATYPE_MISMATCH.1", "", "spark.analysis.type-mismatch"),
        ("AMBIGUOUS_REFERENCE.1", "", "spark.analysis.ambiguous-reference"),
        (None, "streaming to batch mode mismatch", "sdp.mode-mismatch"),
        (None, "unsupported operation", "sdp.unsupported-action"),
        (None, "spark.conf.set mutated session", "spark.session-mutation"),
        ("OUT_OF_MEMORY", "executor out of memory", "spark.executor-oom"),
        (None, "ClassNotFound connector missing", "spark.connector-missing"),
        (None, "Forbidden: cannot list pods", "kubernetes.rbac-denied"),
    ]
    for error_class, message, expected in cases:
        assert any(
            item["id"] == expected for item in diagnose(error_class=error_class, message=message)
        )
