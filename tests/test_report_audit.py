from pathlib import Path

from scripts.report_audit import audit


def test_report_audit_has_evidence_for_resolved_contracts():
    result = audit(Path(__file__).parents[1])
    assert result["passed"] is True
    assert len(result["checks"]) >= 20
