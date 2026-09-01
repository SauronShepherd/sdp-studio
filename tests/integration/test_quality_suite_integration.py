"""Integration boundary for portable quality-suite execution."""

from pathlib import Path

from sdpstudio_core.quality_suite import execute_quality_suite


def test_quality_suite_integrates_with_bounded_rows(tmp_path: Path) -> None:
    suite = tmp_path / "quality.yaml"
    suite.write_text(
        "checks:\n  - id: id_present\n    type: quality.column_rule\n    config:\n      column: id\n      condition: not_null\n",
        encoding="utf-8",
    )
    result = execute_quality_suite(
        suite,
        {"id_present": [{"id": 1}, {"id": None}]},
    )
    assert result["status"] == "failed"
    assert result["checks"][0]["id"] == "id_present"
