import pytest
from sdpstudio_core.quality_suite import (
    QualitySuiteError,
    execute_quality_suite,
    load_quality_suite,
)


def test_quality_suite_loads_and_executes_checks(tmp_path):
    suite = tmp_path / "quality.yaml"
    suite.write_text(
        "checks:\n  - id: unique-orders\n    type: quality.uniqueness\n    config:\n      columns: [id]\n",
        encoding="utf-8",
    )
    assert load_quality_suite(suite)[0]["id"] == "unique-orders"
    result = execute_quality_suite(suite, {"unique-orders": [{"id": 1}, {"id": 1}]})
    assert result["status"] == "failed"
    assert result["checks"][0]["status"] == "failed"


def test_quality_suite_rejects_invalid_shape(tmp_path):
    suite = tmp_path / "quality.yaml"
    suite.write_text("checks: bad\n", encoding="utf-8")
    with pytest.raises(QualitySuiteError, match="checks list"):
        load_quality_suite(suite)


def test_quality_suite_validates_execution_modes(tmp_path):
    suite = tmp_path / "quality.yaml"
    suite.write_text(
        "checks:\n  - id: x\n    type: quality.null_rate\n    mode: scheduled\n", encoding="utf-8"
    )
    assert load_quality_suite(suite)[0]["mode"] == "scheduled"
    suite.write_text(
        "checks:\n  - id: x\n    type: quality.null_rate\n    mode: never\n", encoding="utf-8"
    )
    with pytest.raises(QualitySuiteError, match="mode"):
        load_quality_suite(suite)


def test_quality_suite_filters_by_execution_mode(tmp_path):
    suite = tmp_path / "quality.yaml"
    suite.write_text(
        "checks:\n"
        "  - id: preview-check\n    type: quality.row_count_range\n    mode: preview\n    config: {min: 1}\n"
        "  - id: scheduled-check\n    type: quality.row_count_range\n    mode: scheduled\n    config: {min: 1}\n",
        encoding="utf-8",
    )
    result = execute_quality_suite(
        suite, {"preview-check": [{}], "scheduled-check": [{}]}, mode="preview"
    )
    assert result["mode"] == "preview"
    assert [item["id"] for item in result["checks"]] == ["preview-check"]
