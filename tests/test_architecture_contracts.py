from pathlib import Path

import pytest
import sqlglot
from sdpstudio_codegen import (
    CodegenContext,
    PythonCodegenBackend,
    SqlCodegenBackend,
    choose_target,
    generate_project,
    generate_python_project,
    generate_sql_project,
)
from sdpstudio_core.capabilities import validate_capabilities
from sdpstudio_core.debug import parse_explain_plan, plan_diff
from sdpstudio_core.graph import validate_graph
from sdpstudio_core.ir import pipeline_to_ir
from sdpstudio_core.models import Edge, Node, PipelineDocument, RuntimeCapabilities
from sdpstudio_core.operators import builtin_registry
from sdpstudio_core.persistence import load_yaml, save_yaml, upgrade_yaml


def test_graph_lowers_to_position_independent_ir():
    source = Node(id="source", type="source.table", config={"table": "raw.orders"})
    output = Node(id="output", type="dataset.materialized_view", config={"name": "orders"})
    edge = Edge.model_validate({"from": {"node": "source"}, "to": {"node": "output", "port": "in"}})
    document = PipelineDocument(name="orders", nodes=[source, output], edges=[edge])
    ir = pipeline_to_ir(document)
    assert ir.datasets[0].name == "orders"
    assert ir.datasets[0].origin_node_id == "output"


def test_codegen_backends_consume_canonical_ir_contract(tmp_path: Path):
    source = Node(id="source", type="source.table", config={"table": "raw.orders"})
    output = Node(id="output", type="dataset.materialized_view", config={"name": "orders"})
    edge = Edge.model_validate({"from": {"node": "source"}, "to": {"node": "output", "port": "in"}})
    ir = pipeline_to_ir(PipelineDocument(name="orders", nodes=[source, output], edges=[edge]))
    context = CodegenContext(project_root=tmp_path)
    python_result = PythonCodegenBackend().generate(ir, context)
    sql_result = SqlCodegenBackend().generate(ir, context)
    assert python_result.files and sql_result.files
    assert PythonCodegenBackend().supports(ir).supported
    assert SqlCodegenBackend().supports(ir).supported


def test_custom_source_and_transform_blocks_are_first_class_codegen_operators():
    source = Node(id="source", type="source.custom_pyspark", config={"code": "spark.range(3)"})
    transform = Node(
        id="transform",
        type="transform.pyspark_block",
        config={"code": "$input.filter(F.col('id') > 0)"},
    )
    output = Node(id="output", type="dataset.materialized_view", config={"name": "orders"})
    edges = [
        Edge.model_validate(
            {"from": {"node": "source"}, "to": {"node": "transform", "port": "in"}}
        ),
        Edge.model_validate(
            {"from": {"node": "transform"}, "to": {"node": "output", "port": "in"}}
        ),
    ]
    result = generate_python_project(
        PipelineDocument(nodes=[source, transform, output], edges=edges)
    )
    assert not result.problems
    assert "spark.range(3)" in result.files[0].content
    assert ".filter(F.col('id') > 0)" in result.files[0].content


def test_codegen_support_reports_are_derived_from_ir_operators():
    source = Node(id="source", type="source.custom_pyspark", config={"code": "spark.range(3)"})
    output = Node(id="output", type="dataset.materialized_view", config={"name": "orders"})
    edge = Edge.model_validate({"from": {"node": "source"}, "to": {"node": "output", "port": "in"}})
    ir = pipeline_to_ir(PipelineDocument(name="orders", nodes=[source, output], edges=[edge]))
    report = SqlCodegenBackend().supports(ir)
    assert not report.supported
    assert report.reasons == ("source.custom_pyspark",)


def test_reusable_component_ports_are_first_class_operator_definitions():
    from sdpstudio_core.operators import builtin_registry

    registry = builtin_registry()
    component_input = registry.get("utility.component_input")
    component_output = registry.get("utility.component_output")
    assert [port.name for port in component_input.outputs] == ["out"]
    assert [port.name for port in component_output.inputs] == ["in"]
    assert component_input.config_schema["required"] == ["name"]
    assert component_output.config_schema["required"] == ["name"]


def test_reusable_component_operators_generate_deterministically():
    source = Node(id="input", type="utility.component_input", config={"name": "bronze"})
    output = Node(id="output", type="dataset.materialized_view", config={"name": "silver"})
    edge = Edge.model_validate({"from": {"node": "input"}, "to": {"node": "output", "port": "in"}})
    document = PipelineDocument(name="component", nodes=[source, output], edges=[edge])
    python_result = generate_python_project(document)
    sql_result = generate_sql_project(document)
    assert not python_result.problems
    assert not sql_result.problems
    assert "spark.table('bronze')" in python_result.files[0].content
    assert "SELECT * FROM bronze" in sql_result.files[0].content


def test_capability_validation_is_provider_neutral():
    document = PipelineDocument(
        nodes=[Node(type="dataset.streaming_table", config={"name": "events"})]
    )
    problems = validate_capabilities(document, RuntimeCapabilities(streaming_table=False))
    assert problems[0].code == "SDPS-CAP-001"


def test_yaml_round_trip_is_atomic_and_migrates_v0(tmp_path: Path):
    path = tmp_path / ".sdpstudio" / "pipeline.yaml"
    save_yaml(path, {"schemaVersion": 1, "name": "main"})
    assert load_yaml(path)["schemaVersion"] == 1
    old = tmp_path / "old.yaml"
    save_yaml(old, {"name": "old"})
    assert load_yaml(old)["schemaVersion"] == 1


def test_yaml_upgrade_backs_up_and_migrates_v0_fixture(tmp_path: Path):
    path = tmp_path / ".sdpstudio" / "legacy.yaml"
    save_yaml(path, {"name": "legacy", "nodes": []})

    backup = upgrade_yaml(path)

    assert backup == path.with_name("legacy.yaml.v0.bak")
    assert backup.read_text(encoding="utf-8") == "name: legacy\nnodes: []\n"
    assert load_yaml(path)["schemaVersion"] == 1
    assert load_yaml(path)["name"] == "legacy"


def test_schema_migrations_are_versioned_and_reject_unregistered_steps():
    from sdpstudio_core.persistence import migrate_document

    assert migrate_document({"name": "legacy"}, 0, 1)["schemaVersion"] == 1
    with pytest.raises(ValueError, match="no migration registered"):
        migrate_document({"schemaVersion": 1}, 0, 2)


def test_runtime_extensions_are_typed_and_preserve_extension_details():
    capabilities = RuntimeCapabilities(
        extensions={"spark": {"version": "4.2", "capabilities": ["sdp"]}}
    )
    assert capabilities.extensions["spark"].version == "4.2"
    assert capabilities.extensions["spark"].capabilities == ["sdp"]


def test_sql_backend_is_deterministic_for_supported_slice():
    source = Node(id="source", type="source.table", config={"table": "raw.orders"})
    filt = Node(id="filter", type="transform.filter", config={"expression": "status = 'COMPLETE'"})
    output = Node(id="output", type="dataset.materialized_view", config={"name": "complete_orders"})
    edges = [
        Edge.model_validate({"from": {"node": "source"}, "to": {"node": "filter", "port": "in"}}),
        Edge.model_validate({"from": {"node": "filter"}, "to": {"node": "output", "port": "in"}}),
    ]
    result = generate_sql_project(PipelineDocument(nodes=[source, filt, output], edges=edges))
    assert not result.problems
    assert "CREATE OR REPLACE MATERIALIZED VIEW complete_orders" in result.files[0].content
    assert (
        "SELECT * FROM (SELECT * FROM raw.orders) AS input WHERE status = 'COMPLETE'"
        in result.files[0].content
    )
    sqlglot.parse_one(result.files[0].content.split(" AS\n", 1)[1], read="spark")


def test_sql_query_builder_normalizes_projection_and_predicate_ast():
    from sdpstudio_codegen.sql_backend import _query

    assert _query("SELECT * FROM orders", ["order_id", "amount"], where="amount > 0") == (
        "SELECT order_id, amount FROM (SELECT * FROM orders) AS input WHERE amount > 0"
    )


def test_sql_backend_preserves_streaming_output_kind():
    source = Node(id="source", type="source.table", config={"table": "raw.events"})
    output = Node(id="output", type="dataset.streaming_table", config={"name": "events"})
    edges = [
        Edge.model_validate({"from": {"node": "source"}, "to": {"node": "output", "port": "in"}})
    ]
    result = generate_sql_project(PipelineDocument(nodes=[source, output], edges=edges))
    assert not result.problems
    assert "CREATE OR REPLACE STREAMING TABLE events" in result.files[0].content


def test_python_backend_supports_relational_set_and_column_operators():
    source = Node(id="source", type="source.table", config={"table": "raw.orders"})
    transform = Node(
        id="transform",
        type="transform.replace",
        config={"column": "status", "mapping": {"PENDING": "OPEN"}},
    )
    output = Node(id="output", type="dataset.materialized_view", config={"name": "orders"})
    edges = [
        Edge.model_validate(
            {"from": {"node": "source"}, "to": {"node": "transform", "port": "in"}}
        ),
        Edge.model_validate(
            {"from": {"node": "transform"}, "to": {"node": "output", "port": "in"}}
        ),
    ]
    result = generate_python_project(
        PipelineDocument(nodes=[source, transform, output], edges=edges)
    )
    assert not result.problems
    assert "withColumn('status'" in result.files[0].content


def test_quality_operator_is_generated_as_runtime_metadata_without_actions():
    source = Node(id="source", type="source.table", config={"table": "raw.orders"})
    quality = Node(
        id="quality",
        type="quality.null_rate",
        config={"column": "customer_id", "maxRate": 0.1},
    )
    output = Node(id="output", type="dataset.materialized_view", config={"name": "orders"})
    edges = [
        Edge.model_validate({"from": {"node": "source"}, "to": {"node": "quality", "port": "in"}}),
        Edge.model_validate({"from": {"node": "quality"}, "to": {"node": "output", "port": "in"}}),
    ]
    result = generate_python_project(PipelineDocument(nodes=[source, quality, output], edges=edges))
    assert not result.problems
    assert "count(" not in result.files[0].content
    assert "write" not in result.files[0].content.lower()
    assert "sdpstudio_quality_checks.append" in result.files[0].content
    assert "quality.null_rate" in result.files[0].content


def test_project_runtime_quality_generation_emits_bounded_artifact_hook(tmp_path):
    source = Node(id="source", type="source.table", config={"table": "orders"})
    quality = Node(id="quality", type="quality.null_rate", config={"column": "id", "maxRate": 0.1})
    output = Node(id="output", type="dataset.materialized_view", config={"name": "clean_orders"})
    edges = [
        Edge.model_validate({"from": {"node": "source"}, "to": {"node": "quality", "port": "in"}}),
        Edge.model_validate({"from": {"node": "quality"}, "to": {"node": "output", "port": "in"}}),
    ]
    result = generate_python_project(
        PipelineDocument(nodes=[source, quality, output], edges=edges),
        tmp_path,
        runtime_hooks=True,
    )
    content = result.files[0].content
    assert "_sdpstudio_quality_check" in content
    assert "SDPSTUDIO_QUALITY_SAMPLE_ROWS" in content
    assert "quarantine" in content
    assert "SDPSTUDIO_QUALITY_FAIL_ON_ERROR" in content


def test_project_root_generation_is_portable_by_default(tmp_path):
    source = Node(id="source", type="source.table", config={"table": "orders"})
    quality = Node(id="quality", type="quality.null_rate", config={"column": "id", "maxRate": 0.1})
    output = Node(id="output", type="dataset.materialized_view", config={"name": "orders"})
    result = generate_python_project(
        PipelineDocument(
            nodes=[source, quality, output],
            edges=[
                Edge.model_validate(
                    {"from": {"node": "source"}, "to": {"node": "quality", "port": "in"}}
                ),
                Edge.model_validate(
                    {"from": {"node": "quality"}, "to": {"node": "output", "port": "in"}}
                ),
            ],
        ),
        tmp_path,
    )
    assert not result.problems
    content = result.files[0].content
    assert "_sdpstudio_quality_check" not in content
    assert ".toJSON().collect()" not in content
    assert "sdpstudio_core.quality" not in content


def test_explain_plan_parser_fails_soft_and_supports_diff():
    first = parse_explain_plan("== Physical Plan ==\n*(1) Filter (id > 1)\n+- Scan parquet")
    second = parse_explain_plan(
        "== Physical Plan ==\n*(1) Aggregate\n+- Scan parquet\nunparsed detail"
    )
    assert [item["operator"] for item in first["nodes"]] == ["Filter", "Scan"]
    assert second["raw_lines"] == ["unparsed detail"]
    assert plan_diff(first, second)["changed"] is True


def test_auto_cdc_operator_requires_runtime_capability_and_generates_reference_api():
    source = Node(
        id="source", type="source.table", config={"table": "raw.changes", "streaming": True}
    )
    output = Node(
        id="output",
        type="dataset.auto_cdc_scd1",
        config={"name": "customers", "keys": ["id"], "sequence_by": "updated_at"},
    )
    edge = Edge.model_validate({"from": {"node": "source"}, "to": {"node": "output", "port": "in"}})
    document = PipelineDocument(nodes=[source, output], edges=[edge])
    problems = validate_capabilities(document, RuntimeCapabilities(sdp=True, streaming_table=True))
    assert any("auto_cdc_scd1" in item.message for item in problems)
    result = generate_python_project(document)
    assert not result.problems
    assert "create_auto_cdc_flow" in result.files[0].content


def test_builtin_operator_registry_validates_required_config():
    definition = builtin_registry().get("transform.filter")
    problems = definition.validate_config({}, node_id="filter")
    assert problems[0].code == "SDPS-OPERATOR-001"
    assert definition.inputs[0].name == "in"


def test_operator_registry_exposes_typed_ui_and_extension_metadata():
    definition = builtin_registry().get("transform.filter")
    assert definition.ui_schema["fields"][0]["name"] == "expression"
    assert definition.validator_hook
    assert definition.documentation_key == "operator.transform.filter"
    assert definition.forbidden_capabilities == frozenset()
    assert definition.inputs[0].cardinality == "one"


def test_capability_validation_reports_documented_downgrade_as_warning():
    document = PipelineDocument(
        nodes=[Node(type="dataset.streaming_table", config={"name": "events"})]
    )
    problems = validate_capabilities(
        document,
        RuntimeCapabilities(
            streaming_table=False,
            downgrade_map={"streaming_table": "batch_materialization"},
            portability="portable",
            extensions={"spark": {"version": "4.2"}},
        ),
    )
    assert any(
        problem.code == "SDPS-CAP-002" and problem.severity == "warning" for problem in problems
    )


def test_quality_operator_catalog_covers_range_referential_and_quarantine_tests():
    registry = builtin_registry()
    for operator_id in (
        "quality.row_count_range",
        "quality.referential_sample",
        "quality.quarantine_split",
    ):
        definition = registry.get(operator_id)
        assert definition.outputs
        assert definition.config_schema["type"] == "object"
    reference = next(
        port
        for port in registry.get("quality.referential_sample").inputs
        if port.name == "reference"
    )
    quarantine = next(
        port
        for port in registry.get("quality.quarantine_split").outputs
        if port.name == "quarantine"
    )
    assert reference.optional is True
    assert quarantine.cardinality == "one"


def test_codegen_preserves_quarantine_split_branches():
    source = Node(id="source", type="source.table", config={"table": "events"})
    split = Node(
        id="split",
        type="quality.quarantine_split",
        config={"condition": "not_null", "column": "id", "quarantineName": "bad_events"},
    )
    accepted = Node(id="accepted", type="dataset.materialized_view", config={"name": "events"})
    quarantine = Node(
        id="quarantine", type="dataset.materialized_view", config={"name": "bad_events"}
    )
    edges = [
        Edge.model_validate({"from": {"node": "source"}, "to": {"node": "split", "port": "in"}}),
        Edge.model_validate(
            {
                "from": {"node": "split", "port": "accepted"},
                "to": {"node": "accepted", "port": "in"},
            }
        ),
        Edge.model_validate(
            {
                "from": {"node": "split", "port": "quarantine"},
                "to": {"node": "quarantine", "port": "in"},
            }
        ),
    ]
    document = PipelineDocument(nodes=[source, split, accepted, quarantine], edges=edges)
    python_result = generate_python_project(document)
    assert python_result.files
    content = python_result.files[0].content
    assert "isNotNull()" in content
    assert "isNull()" in content
    sql_result = generate_sql_project(document)
    assert sql_result.files
    sql_content = sql_result.files[0].content
    assert "NOT id IS NULL" in sql_content
    assert "IS NULL" in sql_content


def test_operator_registry_exposes_deterministic_contract_metadata():
    metadata = builtin_registry().get("source.table").contract_metadata()
    assert metadata["id"] == "source.table"
    assert metadata["inputs"] == []
    assert "validator" in metadata["hooks"]
    assert metadata["documentation_key"] == "operator.source.table"


def test_codegen_source_maps_include_deterministic_column_ranges():
    document = PipelineDocument(
        nodes=[
            Node(id="source", type="source.table", config={"table": "events"}),
            Node(id="output", type="dataset.materialized_view", config={"name": "events_out"}),
        ],
        edges=[
            Edge.model_validate(
                {"from": {"node": "source"}, "to": {"node": "output", "port": "in"}}
            )
        ],
    )
    result = generate_python_project(document)
    assert result.problems == []
    assert result.source_map
    assert all(
        item.start_column is not None
        and item.end_column is not None
        and item.start_column >= 1
        and item.end_column > item.start_column
        for item in result.source_map
    )


def test_utility_and_complex_expression_operators_generate_deterministically():
    source = Node(
        id="source",
        type="source.table",
        config={"table": "events"},
    )
    array = Node(
        id="array",
        type="transform.build_array",
        config={"target": "states", "expressions": ["'READY'", "'DONE'"]},
    )
    output = Node(id="output", type="dataset.materialized_view", config={"name": "states"})
    edges = [
        Edge.model_validate(
            {"from": {"node": "source", "port": "out"}, "to": {"node": "array", "port": "in"}}
        ),
        Edge.model_validate(
            {"from": {"node": "array", "port": "out"}, "to": {"node": "output", "port": "in"}}
        ),
    ]
    document = PipelineDocument(nodes=[source, array, output], edges=edges)
    python = generate_project(document, "python").files[0].content
    sql = generate_project(document, "sql").files[0].content
    assert "F.array" in python
    assert "ARRAY('READY', 'DONE')" in sql


def test_custom_code_expression_is_preserved_in_generated_source():
    source = Node(id="source", type="source.table", config={"table": "events"})
    custom = Node(id="custom", type="utility.custom_code", config={"code": "return df"})
    output = Node(id="output", type="dataset.materialized_view", config={"name": "events"})
    edges = [
        Edge.model_validate(
            {"from": {"node": "source", "port": "out"}, "to": {"node": "custom", "port": "in"}}
        ),
        Edge.model_validate(
            {"from": {"node": "custom", "port": "out"}, "to": {"node": "output", "port": "in"}}
        ),
    ]
    result = generate_project(
        PipelineDocument(nodes=[source, custom, output], edges=edges), "python"
    )
    assert not result.problems
    assert "lambda df: (df)" in result.files[0].content


def test_sql_backend_generates_grouped_aggregate():
    source = Node(id="source", type="source.table", config={"table": "raw.orders"})
    aggregate = Node(
        id="aggregate",
        type="transform.aggregate",
        config={
            "groupBy": ["order_date"],
            "aggregations": [{"expression": "sum(amount)", "alias": "revenue"}],
        },
    )
    output = Node(id="output", type="dataset.materialized_view", config={"name": "daily_revenue"})
    edges = [
        Edge.model_validate(
            {"from": {"node": "source"}, "to": {"node": "aggregate", "port": "in"}}
        ),
        Edge.model_validate(
            {"from": {"node": "aggregate"}, "to": {"node": "output", "port": "in"}}
        ),
    ]
    result = generate_sql_project(PipelineDocument(nodes=[source, aggregate, output], edges=edges))
    assert not result.problems
    assert "GROUP BY order_date" in result.files[0].content
    assert "sum(amount) AS revenue" in result.files[0].content


def test_sql_backend_generates_join():
    left = Node(id="left", type="source.table", config={"table": "raw.orders"})
    right = Node(id="right", type="source.table", config={"table": "raw.customers"})
    join = Node(
        id="join",
        type="transform.join",
        config={"how": "left", "condition": "left_input.customer_id = right_input.id"},
    )
    output = Node(id="output", type="dataset.materialized_view", config={"name": "enriched_orders"})
    edges = [
        Edge.model_validate({"from": {"node": "left"}, "to": {"node": "join", "port": "left"}}),
        Edge.model_validate({"from": {"node": "right"}, "to": {"node": "join", "port": "right"}}),
        Edge.model_validate({"from": {"node": "join"}, "to": {"node": "output", "port": "in"}}),
    ]
    result = generate_sql_project(PipelineDocument(nodes=[left, right, join, output], edges=edges))
    assert not result.problems
    assert "LEFT JOIN" in result.files[0].content


def test_codegen_planner_dispatches_explicit_target():
    document = PipelineDocument(nodes=[Node(type="source.table", config={"table": "raw.orders"})])
    assert generate_project(document, "sql").files[0].path.endswith(".sql")
    assert choose_target("auto", sql_supported=False) == "python"


def test_mixed_language_planner_assigns_outputs_with_deterministic_reasons():
    from sdpstudio_codegen import plan_pipeline

    source = Node(id="source", type="source.table", config={"table": "raw.orders"})
    sql_output = Node(id="sql-output", type="dataset.materialized_view", config={"name": "orders"})
    custom = Node(id="custom", type="utility.custom_code", config={"code": "return input"})
    python_output = Node(
        id="python-output", type="dataset.materialized_view", config={"name": "enriched"}
    )
    document = PipelineDocument(
        nodes=[source, sql_output, custom, python_output],
        edges=[
            Edge.model_validate(
                {"from": {"node": "source"}, "to": {"node": "sql-output", "port": "in"}}
            ),
            Edge.model_validate(
                {"from": {"node": "source"}, "to": {"node": "custom", "port": "in"}}
            ),
            Edge.model_validate(
                {"from": {"node": "custom"}, "to": {"node": "python-output", "port": "in"}}
            ),
        ],
    )
    plan = plan_pipeline(document)
    assert [(item.dataset_id, item.language) for item in plan.assignments] == [
        ("sql-output", "sql"),
        ("python-output", "python"),
    ]
    assert plan.assignments[1].reasons == ("custom code requires the Python backend",)

    explicit_sql = plan_pipeline(document, "sql")
    assert any(problem.code == "SDPS-CODEGEN-001" for problem in explicit_sql.problems)


def test_posexplode_is_catalogued_and_generated_for_both_targets():
    from sdpstudio_core.operators import operator_catalog

    assert "transform.posexplode" in operator_catalog()
    document = PipelineDocument(
        nodes=[
            Node(id="source", type="source.table", config={"table": "events"}),
            Node(
                id="explode",
                type="transform.posexplode",
                config={"column": "items", "position": "item_pos", "target": "item"},
            ),
            Node(id="output", type="dataset.materialized_view", config={"name": "items"}),
        ],
        edges=[
            Edge.model_validate(
                {"from": {"node": "source", "port": "out"}, "to": {"node": "explode", "port": "in"}}
            ),
            Edge.model_validate(
                {"from": {"node": "explode", "port": "out"}, "to": {"node": "output", "port": "in"}}
            ),
        ],
    )
    python = generate_project(document, "python").files[0].content
    sql = generate_project(document, "sql").files[0].content
    assert "posexplode" in python
    assert "LATERAL VIEW posexplode" in sql


def test_graph_validation_honors_optional_input_port_metadata():
    document = PipelineDocument(
        nodes=[
            Node(id="source", type="source.table", config={"table": "raw.items"}),
            Node(id="sample", type="quality.referential_sample", config={}),
        ],
        edges=[
            Edge.model_validate(
                {"from": {"node": "source"}, "to": {"node": "sample", "port": "in"}}
            )
        ],
    )
    problems = validate_graph(document)
    assert not any(
        "reference" in problem.message and "connected" in problem.message for problem in problems
    )
