from sdpstudio_codegen import generate_preview_script
from sdpstudio_core.debug import parse_explain_plan
from sdpstudio_core.models import Edge, Node, PipelineDocument, PortRef


def test_batch_preview_script_is_bounded_and_compiles():
    source = Node(type="source.table", config={"table": "raw.orders", "streaming": False})
    filt = Node(type="transform.filter", config={"expression": "amount > 10"})
    out = Node(type="dataset.materialized_view", config={"name": "large_orders"})
    doc = PipelineDocument(
        name="preview",
        nodes=[source, filt, out],
        edges=[
            Edge(**{"from": PortRef(node=source.id), "to": PortRef(node=filt.id, port="in")}),
            Edge(**{"from": PortRef(node=filt.id), "to": PortRef(node=out.id, port="in")}),
        ],
    )
    script, problems = generate_preview_script(doc, filt.id, limit=37)
    assert script is not None
    assert not [p for p in problems if p.severity == "error"]
    assert ".filter(F.expr('amount > 10'))" in script
    assert ".limit(37).toJSON().collect()" in script
    compile(script, "<test-preview>", "exec")


def test_preview_plan_capture_is_explicit_and_persisted_in_payload():
    source = Node(type="source.table", config={"table": "raw.orders", "streaming": False})
    output = Node(type="dataset.materialized_view", config={"name": "orders"})
    script, problems = generate_preview_script(
        PipelineDocument(
            name="plan",
            nodes=[source, output],
            edges=[
                Edge(**{"from": PortRef(node=source.id), "to": PortRef(node=output.id, port="in")})
            ],
        ),
        source.id,
        include_plan=True,
    )
    assert script is not None
    assert not [problem for problem in problems if problem.severity == "error"]
    assert '__svp_df.explain(mode="extended")' in script
    assert '__svp_payload["plan"]' in script


def test_preview_trace_instrumentation_adds_bounded_spark_row_identity():
    source = Node(type="source.table", config={"table": "raw.orders"})
    script, problems = generate_preview_script(
        PipelineDocument(name="trace", nodes=[source]), source.id, include_trace=True, limit=9
    )
    assert script is not None
    assert not [problem for problem in problems if problem.severity == "error"]
    assert "monotonically_increasing_id" in script
    assert "trace_rows" in script
    assert "'trace_instrumentation': 'spark_monotonically_increasing_id'" in script
    assert "'trace_nodes': {" in script
    compile(script, "<test-trace-preview>", "exec")


def test_preview_runtime_profile_is_opt_in_and_bounded():
    source = Node(type="source.table", config={"table": "raw.orders"})
    script, problems = generate_preview_script(
        PipelineDocument(name="profile", nodes=[source]),
        source.id,
        include_profile=True,
        profile_max_rows=17,
        profile_max_columns=3,
        profile_top_values=2,
    )
    assert script is not None
    assert not [problem for problem in problems if problem.severity == "error"]
    assert ".limit(17).toJSON().collect()" in script
    assert "profile_rows(__svp_profile_rows, max_rows=17, max_columns=3, top_values=2)" in script


def test_preview_sampling_is_deterministic_and_bounded():
    source = Node(type="source.table", config={"table": "raw.orders"})
    script, problems = generate_preview_script(
        PipelineDocument(name="sample", nodes=[source]),
        source.id,
        sampling_fraction=0.25,
        seed=1234,
        limit=11,
    )
    assert not [problem for problem in problems if problem.severity == "error"]
    assert "fraction=0.25" in script
    assert "seed=1234" in script
    assert ".limit(11).toJSON().collect()" in script


def test_sink_preview_requires_explicit_confirmation():
    sink = Node(type="sink.table", config={"table": "raw.orders"})
    script, problems = generate_preview_script(PipelineDocument(name="sink", nodes=[sink]), sink.id)
    assert script is None
    assert any(problem.code == "SDPS-PREVIEW-020" for problem in problems)


def test_preview_emits_bounded_result_metrics_and_elapsed_time():
    source = Node(type="source.table", config={"table": "raw.orders"})
    script, problems = generate_preview_script(
        PipelineDocument(name="metrics", nodes=[source]),
        source.id,
        limit=10,
        include_profile=True,
    )
    assert not [problem for problem in problems if problem.severity == "error"]
    assert script is not None
    assert '"metrics": {"row_count": len(__svp_rows)}' in script
    assert '"elapsed_ms"' in script
    assert '__svp_payload["metrics"]["profile_bounded"] = True' in script


def test_captured_plan_parser_produces_stable_runtime_nodes():
    parsed = parse_explain_plan("== Physical Plan ==\n*(1) Filter (id > 1)\n+- Scan parquet")
    assert parsed["phases"] == ["physical"]
    assert [node["operator"] for node in parsed["nodes"]] == ["Filter", "Scan"]
    assert [node["id"] for node in parsed["nodes"]] == ["plan-1", "plan-2"]


def test_preview_stops_at_declared_dataset_boundary():
    source = Node(type="source.table", config={"table": "raw.orders", "streaming": False})
    bronze = Node(type="dataset.materialized_view", config={"name": "bronze_orders"})
    filt = Node(type="transform.filter", config={"expression": "amount > 10"})
    doc = PipelineDocument(
        name="preview",
        nodes=[source, bronze, filt],
        edges=[
            Edge(**{"from": PortRef(node=source.id), "to": PortRef(node=bronze.id, port="in")}),
            Edge(**{"from": PortRef(node=bronze.id), "to": PortRef(node=filt.id, port="in")}),
        ],
    )
    script, problems = generate_preview_script(doc, filt.id)
    assert script is not None
    assert not [p for p in problems if p.severity == "error"]
    assert "spark.table('bronze_orders')" in script
    assert "spark.table('raw.orders')" not in script


def test_unmaterialized_stream_preview_is_rejected():
    source = Node(
        type="source.kafka",
        config={"bootstrapServers": "kafka:9092", "subscribe": "orders", "options": {}},
    )
    doc = PipelineDocument(name="preview", nodes=[source])
    script, problems = generate_preview_script(doc, source.id)
    assert script is None
    assert any(p.code == "SDPS-PREVIEW-004" for p in problems)


def test_preview_keeps_secret_references_out_of_generated_source():
    source = Node(
        type="source.file",
        config={"path": "secret://ORDERS_PATH", "format": "json", "options": {}},
    )
    script, problems = generate_preview_script(
        PipelineDocument(name="preview", nodes=[source]), source.id
    )
    assert script is not None
    assert not [problem for problem in problems if problem.severity == "error"]
    assert "os.environ['ORDERS_PATH']" in script
    assert "secret://" not in script


def test_preview_keeps_jdbc_secret_references_out_of_source():
    jdbc = Node(
        type="source.jdbc",
        config={"url": "secret://JDBC_URL", "dbtable": "orders", "options": {}},
    )
    script, problems = generate_preview_script(PipelineDocument(nodes=[jdbc]), jdbc.id)
    assert script is not None
    assert not [problem for problem in problems if problem.severity == "error"]
    assert "os.environ['JDBC_URL']" in script
    assert "secret://" not in script
