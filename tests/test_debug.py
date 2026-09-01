import os

import pytest
from sdpstudio_core.debug import (
    evaluate_schema_contract,
    execute_row_trace,
    plan_diff,
    profile_diff,
    profile_rows,
    schema_diff,
    schema_fingerprint,
    summarize_spark_events,
    summarize_streaming_events,
)
from sdpstudio_core.models import Edge, Node, PipelineDocument
from sdpstudio_runners.local import _ingest_plan_artifacts


def test_event_log_skew_summary():
    events = [
        {
            "Event": "SparkListenerStageSubmitted",
            "Stage Info": {"Stage ID": 3, "Stage Name": "join"},
        },
        {
            "Event": "SparkListenerTaskEnd",
            "Stage ID": 3,
            "Task Info": {"Launch Time": 0, "Finish Time": 100},
            "Task Metrics": {
                "Executor Run Time": 90,
                "Memory Bytes Spilled": 128,
                "Disk Bytes Spilled": 64,
                "Executor CPU Time": 5000,
            },
        },
        {
            "Event": "SparkListenerTaskEnd",
            "Stage ID": 3,
            "Task Info": {"Launch Time": 0, "Finish Time": 110},
            "Task Metrics": {"Executor Run Time": 100},
        },
        {
            "Event": "SparkListenerTaskEnd",
            "Stage ID": 3,
            "Task Info": {"Launch Time": 0, "Finish Time": 900},
            "Task Metrics": {"Executor Run Time": 880},
        },
    ]
    result = summarize_spark_events(events)
    stage = result["stages"][0]
    assert stage["stage_id"] == 3
    assert stage["skew_score"] > 5
    assert stage["diagnostic"] == "severe skew"
    assert stage["p95_task_ms"] == 900
    assert stage["memory_bytes_spilled"] == 128
    assert stage["disk_bytes_spilled"] == 64
    assert stage["executor_cpu_time_ns"] == 5000
    assert stage["scheduler_delay_ms"] == 40


def test_explain_plan_preserves_spark_plan_phases_and_python_udfs():
    from sdpstudio_core.debug import parse_explain_plan

    result = parse_explain_plan(
        "== Parsed Logical Plan ==\nProject\n== Physical Plan ==\nBatchEvalPython\n"
    )
    assert result["phases"] == ["parsed", "physical"]
    assert [node["phase"] for node in result["nodes"]] == ["parsed", "physical"]
    assert result["nodes"][1]["operator"] == "BatchEvalPython"


def test_spark_event_stream_keeps_bounded_task_reservoir():
    from sdpstudio_core.debug import summarize_spark_event_stream

    def events():
        yield {
            "Event": "SparkListenerStageSubmitted",
            "Stage Info": {"Stage ID": 1, "Stage Name": "scan"},
        }
        for value in range(20):
            yield {
                "Event": "SparkListenerTaskEnd",
                "Stage ID": 1,
                "Task Info": {"Launch Time": 0, "Finish Time": value + 1},
                "Task Metrics": {"Executor Run Time": value + 1},
            }

    result = summarize_spark_event_stream(events(), max_tasks_per_stage=3)
    assert result["stages"][0]["task_count"] == 3


def test_explain_plan_normalizes_unstable_ids_and_extracts_execution_metadata():
    from sdpstudio_core.debug import parse_explain_plan

    result = parse_explain_plan(
        "== Physical Plan ==\n"
        "*(1) BroadcastHashJoin [id#12], [id#99], Inner\n"
        "+- Exchange hashpartitioning(id, 200) id=42\n"
    )
    assert result["nodes"][0]["join_strategy"] == "broadcast"
    assert result["nodes"][1]["partitioning"] == 200
    assert "#?" in result["normalized_nodes"][0]["raw"]
    assert "id=?" in result["nodes"][1]["exchange"]


def test_plan_diff_reports_execution_strategy_partition_and_metric_changes():
    result = plan_diff(
        {
            "nodes": [
                {
                    "operator": "SortMergeJoin",
                    "phase": "physical",
                    "join_strategy": "sort_merge",
                    "exchange": "hashpartitioning(id, 200)",
                    "partitioning": 200,
                    "metrics": {"duration_ms": 10},
                }
            ]
        },
        {
            "nodes": [
                {
                    "operator": "BroadcastHashJoin",
                    "phase": "physical",
                    "join_strategy": "broadcast_hash",
                    "exchange": None,
                    "partitioning": 1,
                    "metrics": {"duration_ms": 4},
                }
            ]
        },
    )
    assert result["join_strategy_changes"][0]["after"] == "broadcast_hash"
    assert result["operations"][0]["op"] == "replace"
    assert result["exchange_changes"]
    assert result["partitioning_changes"][0]["after"] == 1
    assert result["metric_changes"][0]["after"] == {"duration_ms": 4}


def test_generated_line_maps_to_most_specific_visual_node():
    from sdpstudio_runners.local import _generated_line_from_log, _node_for_generated_line

    mappings = [
        {
            "node_id": "output",
            "file": "transformations/generated.py",
            "start_line": 10,
            "end_line": 20,
        },
        {
            "node_id": "filter",
            "file": "transformations/generated.py",
            "start_line": 14,
            "end_line": 14,
        },
    ]
    assert (
        _generated_line_from_log('File "/tmp/transformations/generated.py", line 14, in orders')
        == 14
    )
    assert _node_for_generated_line(mappings, 14)["node_id"] == "filter"


def test_schema_fingerprint_and_diff_are_deterministic():
    before = [{"name": "id", "type": "integer"}, {"name": "amount", "type": "double"}]
    after = [{"name": "id", "type": "long"}, {"name": "status", "type": "string"}]
    assert schema_fingerprint(before) == schema_fingerprint(list(reversed(before)))
    diff = schema_diff(before, after)
    assert diff["added"] == ["status"]
    assert diff["removed"] == ["amount"]
    assert diff["compatible"] is False


def test_schema_diff_reports_nested_paths_and_type_compatibility():
    before = [{"name": "payload", "type": "struct", "fields": [{"name": "id", "type": "integer"}]}]
    after = [
        {
            "name": "payload",
            "type": "struct",
            "fields": [{"name": "id", "type": "long"}, {"name": "label", "type": "string"}],
        }
    ]
    diff = schema_diff(before, after)
    assert diff["nested_changed"][0]["path"] == "payload.id"
    assert diff["nested_added"] == ["payload.label"]
    assert diff["compatible"] is False


def test_schema_contract_policy_distinguishes_warn_and_block():
    diff = schema_diff([{"name": "id", "type": "long"}], [])
    assert evaluate_schema_contract(diff, mode="block")["status"] == "blocked"
    assert evaluate_schema_contract(diff, mode="warn")["status"] == "warned"
    assert evaluate_schema_contract({"added": ["new_col"]}, allow_added=True)["status"] == "passed"


def test_profile_rows_is_bounded_and_null_aware():
    result = profile_rows(
        [{"id": 1, "amount": 3.5}, {"id": 2, "amount": None}, {"id": 1, "amount": 5.0}]
    )
    assert result["row_count"] == 3
    assert result["columns"]["amount"]["null_count"] == 1
    assert result["columns"]["amount"]["min"] == 3.5
    assert result["columns"]["id"]["distinct_count"] == 2
    limited = profile_rows(
        [{"a": 1, "b": 2}, {"a": 1, "b": 3}], max_rows=1, max_columns=1, top_values=1
    )
    assert limited["row_count"] == 1
    assert list(limited["columns"]) == ["a"]
    assert limited["limits"]["top_values"] == 1


def test_profile_diff_is_deterministic_and_marks_missing_metrics():
    before = profile_rows([{"id": 1, "amount": 2.0}])
    after = profile_rows([{"id": 1, "amount": 4.0, "status": "ok"}, {"id": 2, "amount": 6.0}])
    result = profile_diff(before, after)
    assert result["status"] == "insufficient_data"
    assert result["added_columns"] == ["status"]
    assert result["columns"]["amount"]["metrics"]["max"]["delta"] == 4.0
    assert result["columns"]["status"]["reason"] == "column_added_or_removed"


def test_execute_row_trace_reports_filter_survival_and_is_bounded():
    from sdpstudio_core.models import Edge, Node, PipelineDocument

    source = Node(id="source", type="source.table", config={"table": "orders"})
    filt = Node(id="filter", type="transform.filter", config={"expression": "amount > 10"})
    document = PipelineDocument(
        nodes=[source, filt],
        edges=[Edge.model_validate({"from": {"node": "source"}, "to": {"node": "filter"}})],
    )
    result = execute_row_trace(
        document, "filter", [{"id": 1, "amount": 12}, {"id": 2, "amount": 3}], max_rows=1
    )
    assert result["trace_mode"] == "sample"
    assert result["execution_backed"] is False
    assert result["provenance"] == "caller_supplied_rows"
    assert result["ok"] is True
    assert result["rows"] == [{"id": 1, "amount": 12}]
    assert result["steps"][-1]["output_count"] == 1


def test_execute_row_trace_handles_rename_and_cast_without_losing_rows():
    from sdpstudio_core.models import Edge, Node, PipelineDocument

    document = PipelineDocument(
        nodes=[
            Node(id="source", type="source.table", config={}),
            Node(id="rename", type="transform.rename", config={"mapping": {"id": "order_id"}}),
            Node(
                id="cast", type="transform.cast", config={"column": "order_id", "dataType": "long"}
            ),
        ],
        edges=[
            Edge.model_validate({"from": {"node": "source"}, "to": {"node": "rename"}}),
            Edge.model_validate({"from": {"node": "rename"}, "to": {"node": "cast"}}),
        ],
    )
    result = execute_row_trace(document, "cast", [{"id": "7"}])
    assert result["ok"] is True
    assert result["rows"] == [{"order_id": 7}]


def test_execute_row_trace_aggregates_with_bounded_contribution_summary():
    from sdpstudio_core.models import Edge, Node, PipelineDocument

    document = PipelineDocument(
        nodes=[
            Node(id="source", type="source.table", config={}),
            Node(
                id="aggregate",
                type="transform.aggregate",
                config={
                    "groupBy": ["kind"],
                    "aggregations": [{"expression": "sum(amount)", "alias": "total"}],
                },
            ),
        ],
        edges=[Edge.model_validate({"from": {"node": "source"}, "to": {"node": "aggregate"}})],
    )
    result = execute_row_trace(
        document,
        "aggregate",
        [
            {"kind": "a", "amount": 2},
            {"kind": "a", "amount": 3},
            {"kind": "a", "amount": 4},
            {"kind": "a", "amount": 1},
            {"kind": "b", "amount": 5},
        ],
        max_rows=5,
    )
    assert result["rows"] == [{"kind": "a", "total": 10}, {"kind": "b", "total": 5}]
    assert result["steps"][-1]["trace_summary"][0]["trace_overflow"] is True


def test_execute_row_trace_marks_custom_code_boundaries_unknown():
    from sdpstudio_core.models import Edge, Node, PipelineDocument

    document = PipelineDocument(
        nodes=[
            Node(id="source", type="source.table", config={}),
            Node(id="custom", type="utility.custom_code", config={"code": "return df"}),
            Node(id="output", type="dataset.materialized_view", config={}),
        ],
        edges=[
            Edge.model_validate({"from": {"node": "source"}, "to": {"node": "custom"}}),
            Edge.model_validate({"from": {"node": "custom"}, "to": {"node": "output"}}),
        ],
    )
    result = execute_row_trace(document, "output", [{"id": 1}])
    assert result["ok"] is True
    assert result["steps"][1]["trace_status"] == "unknown"
    assert result["steps"][2]["trace_status"] == "unknown"
    assert result["unsupported"] == [{"node_id": "custom", "type": "utility.custom_code"}]


def test_execute_row_trace_keeps_multi_source_samples_separate():
    document = PipelineDocument(
        name="multi-source-trace",
        nodes=[
            Node(id="left", type="source.table", config={}),
            Node(id="right", type="source.table", config={}),
            Node(id="join", type="transform.join", config={"condition": "left.id = right.id"}),
        ],
        edges=[
            Edge(**{"from": {"node": "left"}, "to": {"node": "join", "port": "left"}}),
            Edge(**{"from": {"node": "right"}, "to": {"node": "join", "port": "right"}}),
        ],
    )

    result = execute_row_trace(
        document,
        "join",
        [],
        rows_by_source={
            "left": [{"id": 1, "left_value": "L"}],
            "right": [{"id": 1, "right_value": "R"}],
        },
    )

    assert result["ok"] is True
    assert result["rows"] == [{"id": 1, "left_value": "L", "right_value": "R"}]


def test_event_log_ingestion_keeps_summary_and_raw_artifact(tmp_path):
    import json

    from sdpstudio_runners.local import _ingest_recent_event_logs

    project = tmp_path / "project"
    event_log = project / ".sdpstudio" / "runtime" / "event-logs" / "01-run" / "events.json"
    event_log.parent.mkdir(parents=True)
    event_log.write_text(
        json.dumps({"Event": "SparkListenerStageSubmitted", "Stage Info": {"Stage ID": 1}}) + "\n",
        encoding="utf-8",
    )
    result = _ingest_recent_event_logs(project, event_log.stat().st_mtime - 1, "01-run")
    assert result is not None
    assert result["event_count"] == 1
    raw = (
        project
        / ".sdpstudio"
        / "runtime"
        / "run-artifacts"
        / "01-run"
        / "event-logs"
        / "01-run"
        / "events.json"
    )
    assert raw.exists()
    assert result["raw_artifacts"] == ["event-logs/01-run/events.json"]
    event_log.write_text(
        event_log.read_text(encoding="utf-8")
        + json.dumps({"Event": "SparkListenerStageSubmitted", "Stage Info": {"Stage ID": 2}})
        + "\n",
        encoding="utf-8",
    )
    resumed = _ingest_recent_event_logs(project, event_log.stat().st_mtime - 1, "01-run")
    assert resumed is not None
    assert resumed["event_count"] == 1
    assert (
        project / ".sdpstudio" / "runtime" / "run-artifacts" / "01-run" / "event-log-offsets.json"
    ).exists()


def test_profile_rows_includes_distribution_metrics():
    result = profile_rows(
        [
            {"amount": 2.0, "status": "ok"},
            {"amount": 4.0, "status": "ok"},
            {"amount": 6.0, "status": "bad"},
        ]
    )
    assert result["columns"]["amount"]["mean"] == 4.0
    assert result["columns"]["amount"]["stddev"] > 0
    assert result["columns"]["status"]["top_values"][0] == {"value": "'ok'", "count": 2}


def test_profile_rows_can_omit_sensitive_distribution_metrics():
    result = profile_rows(
        [{"amount": 2.0, "status": "private"}, {"amount": 4.0, "status": "private"}],
        include_sensitive_metrics=False,
    )
    assert result["columns"]["amount"]["count"] == 2
    assert "mean" not in result["columns"]["amount"]
    assert "top_values" not in result["columns"]["status"]


def test_skew_thresholds_are_configurable_and_validated():
    events = [{"Event": "SparkListenerStageSubmitted", "Stage Info": {"Stage ID": 1}}]
    result = summarize_spark_events(events, moderate_skew_ratio=2.5, severe_skew_ratio=7.5)
    assert result["stages"][0]["diagnostic"] == "balanced/unknown"
    with pytest.raises(ValueError):
        summarize_spark_events(events, moderate_skew_ratio=5, severe_skew_ratio=2)


def test_streaming_diagnostics_extract_progress_watermark_state_and_checkpoint():
    result = summarize_streaming_events(
        [
            {
                "Event": "SparkListenerStreamingQueryProgress",
                "checkpointLocation": "file:///checkpoints/orders",
                "progress": {
                    "id": "query-1",
                    "timestamp": "2026-08-24T00:00:00Z",
                    "batchId": 4,
                    "inputRowsPerSecond": 12.5,
                    "processedRowsPerSecond": 10.0,
                    "numInputRows": 25,
                    "eventTime": {"watermark": "2026-08-24T00:00:00Z"},
                    "stateOperators": [
                        {"operatorName": "stateStore", "numRowsTotal": 8, "memoryUsedBytes": 512}
                    ],
                },
            }
        ]
    )
    assert result["checkpoint_paths"] == ["file:///checkpoints/orders"]
    latest = result["queries"][0]["latest"]
    assert latest["processed_rows_per_second"] == 10.0
    assert latest["watermark"].endswith("Z")
    assert latest["state_operators"][0]["num_rows_total"] == 8


def test_run_plan_artifacts_are_parsed_and_normalized(tmp_path):
    plan_dir = tmp_path / ".sdpstudio" / "runtime" / "run-artifacts" / "run-1" / "plans"
    plan_dir.mkdir(parents=True)
    (plan_dir / "node-2.json").write_text(
        '{"node_id":"node-2","raw":"== Physical Plan ==\\n*(1) Filter (id > 1)\\n+- Scan parquet"}',
        encoding="utf-8",
    )

    result = _ingest_plan_artifacts(tmp_path, "run-1")

    assert result is not None
    assert result["source"] == "spark_dataframe_explain"
    assert result["plans"][0]["parsed"]["nodes"][0]["operator"] == "Filter"
    assert (plan_dir.parent / "plan.json").exists()


@pytest.mark.skipif(
    os.environ.get("SDPSTUDIO_RUN_SPARK_TRACE_TESTS") != "1",
    reason="Opt-in Spark integration test; requires a configured Spark 4.2 runtime",
)
def test_execute_row_trace_spark_subgraph_supports_join_and_aggregate():
    pytest.importorskip("pyspark")
    from sdpstudio_core.debug import execute_row_trace_spark

    left = Node(id="left", type="source.table", config={"table": "left"})
    right = Node(id="right", type="source.table", config={"table": "right"})
    join = Node(id="join", type="transform.join", config={"condition": "left.id = right.id"})
    aggregate = Node(
        id="aggregate",
        type="transform.aggregate",
        config={
            "groupBy": ["id"],
            "aggregations": [{"expression": "count(*)", "alias": "n"}],
        },
    )
    document = PipelineDocument(
        nodes=[left, right, join, aggregate],
        edges=[
            Edge.model_validate({"from": {"node": "left"}, "to": {"node": "join", "port": "left"}}),
            Edge.model_validate(
                {"from": {"node": "right"}, "to": {"node": "join", "port": "right"}}
            ),
            Edge.model_validate(
                {"from": {"node": "join"}, "to": {"node": "aggregate", "port": "in"}}
            ),
        ],
    )
    result = execute_row_trace_spark(
        document,
        "aggregate",
        [],
        rows_by_source={"left": [{"id": 1}, {"id": 2}], "right": [{"id": 2}, {"id": 3}]},
    )
    assert result["execution_backed"] is True
    assert result["trace_mode"] == "spark_subgraph"
    assert result["rows"] == [{"id": 2, "n": 1}]
