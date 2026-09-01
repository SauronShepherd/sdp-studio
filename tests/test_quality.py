from sdpstudio_core.quality import evaluate_quality


def test_quality_null_rate_and_uniqueness_are_deterministic():
    rows = [{"id": 1, "value": None}, {"id": 1, "value": "ok"}]
    nulls = evaluate_quality("quality.null_rate", {"column": "value", "maxRate": 0.25}, rows)
    unique = evaluate_quality("quality.uniqueness", {"columns": ["id"]}, rows)
    assert nulls["status"] == "failed"
    assert unique["status"] == "failed"


def test_quality_quarantine_split_preserves_bounded_rows():
    result = evaluate_quality(
        "quality.quarantine_split",
        {"column": "id", "condition": "not_null"},
        [{"id": 1}, {"id": None}],
    )
    assert result["status"] == "failed"
    assert result["rows"] == [{"id": 1}]
    assert result["quarantine"] == [{"id": None}]


def test_quality_schema_profile_and_referential_checks_are_explicit():
    rows = [{"id": 1, "value": "ok"}, {"id": 2, "value": None}]
    schema = evaluate_quality(
        "quality.schema_contract", {"schema": [{"name": "id"}, {"name": "value"}]}, rows
    )
    profile = evaluate_quality("quality.profile_probe", {"columns": ["value"]}, rows)
    refs = evaluate_quality(
        "quality.referential_sample", {"columns": ["id"], "referenceRows": [{"id": 1}]}, rows
    )
    assert schema["status"] == "passed"
    assert profile["profile"]["row_count"] == 2
    assert refs["status"] == "failed"
