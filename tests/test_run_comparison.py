from sdpstudio_server.run_comparison import (
    duration_seconds,
    node_diffs,
    schema_timeline,
    stage_metric_deltas,
)


def test_run_comparison_duration_and_stage_deltas_are_deterministic():
    assert (
        duration_seconds(
            {"started_at": "2026-01-01T00:00:00+00:00", "finished_at": "2026-01-01T00:00:02+00:00"}
        )
        == 2
    )
    result = stage_metric_deltas(
        {"stages": [{"stage_id": 2, "shuffle_read_bytes": 10, "shuffle_write_bytes": 4}]},
        {"stages": [{"stage_id": 2, "shuffle_read_bytes": 15, "shuffle_write_bytes": 9}]},
    )
    assert result["stages"][0]["shuffle_read_bytes_delta"] == 5
    assert result["stages"][0]["shuffle_write_bytes_delta"] == 5


def test_run_comparison_node_diffs_report_schema_and_quality_changes():
    schemas, quality = node_diffs(
        [
            {
                "node_id": "n1",
                "schema": [{"name": "id", "type": "long"}],
                "profile": {"row_count": 1},
            }
        ],
        [
            {
                "node_id": "n1",
                "schema": [{"name": "id", "type": "string"}],
                "profile": {"row_count": 2},
            }
        ],
    )
    assert schemas["n1"]["available"] is True
    assert schemas["n1"]["diff"]["changed"]
    assert quality["n1"]["diff"]["before_row_count"] == 1
    assert quality["n1"]["diff"]["after_row_count"] == 2


def test_schema_timeline_tracks_persisted_node_changes():
    runs = [
        {"id": "run-1", "created_at": "2026-01-01T00:00:00+00:00"},
        {"id": "run-2", "created_at": "2026-01-02T00:00:00+00:00"},
    ]
    snapshots = {
        "run-1": [{"node_id": "orders", "schema": [{"name": "id", "type": "long"}]}],
        "run-2": [{"node_id": "orders", "schema": [{"name": "id", "type": "string"}]}],
    }
    timeline = schema_timeline(runs, snapshots)
    assert len(timeline) == 2
    assert timeline[0]["changed"] is False
    assert timeline[1]["changed"] is True
    assert timeline[1]["diff"]["changed"][0]["name"] == "id"
