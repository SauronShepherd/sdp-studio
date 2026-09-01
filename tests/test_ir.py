from sdpstudio_core.ir import lower_pipeline, pipeline_to_ir
from sdpstudio_core.models import (
    Edge,
    EnvironmentReference,
    Node,
    Parameter,
    PipelineDocument,
    ProjectMetadata,
)


def test_lowering_builds_deterministic_typed_ir():
    document = PipelineDocument(
        pipelineId="pipeline-1",
        name="orders",
        nodes=[
            Node(id="source", type="source.table", config={"table": "orders"}),
            Node(id="filter", type="transform.filter", config={"expression": "amount > 0"}),
            Node(
                id="output",
                type="dataset.materialized_view",
                config={"name": "clean_orders", "password": "secret://DB_PASSWORD"},
            ),
        ],
        edges=[
            Edge(id="e2", **{"from": {"node": "filter"}, "to": {"node": "output", "port": "in"}}),
            Edge(id="e1", **{"from": {"node": "source"}, "to": {"node": "filter", "port": "in"}}),
        ],
    )
    first = lower_pipeline(document)
    second = lower_pipeline(document)
    assert first.pipeline == second.pipeline
    assert [node.id for node in first.pipeline.nodes] == ["source", "filter", "output"]
    assert first.pipeline.nodes[-1].mode == "batch"
    assert [ref.name for ref in first.pipeline.secrets] == ["DB_PASSWORD"]
    restored = first.pipeline.graph_view()
    assert restored.nodes[0].type == "source.table"
    assert not hasattr(restored.nodes[0], "position")
    assert [edge.id for edge in restored.edges] == ["e1", "e2"]
    assert pipeline_to_ir(document) == first.pipeline


def test_codegen_uses_ir_lowering_path():
    from sdpstudio_codegen import generate_project

    document = PipelineDocument(
        nodes=[
            Node(id="source", type="source.table", config={"table": "orders"}),
            Node(id="output", type="dataset.materialized_view", config={"name": "orders"}),
        ],
        edges=[
            Edge(id="edge", **{"from": {"node": "source"}, "to": {"node": "output", "port": "in"}})
        ],
    )
    python_result = generate_project(document, "python")
    sql_result = generate_project(document, "sql")
    assert not python_result.problems
    assert not sql_result.problems
    assert "orders" in python_result.files[0].content
    assert "orders" in sql_result.files[0].content
    assert python_result.source_map[0].object_id == "node:source:definition"
    assert python_result.source_map[0].start_column == 1
    assert python_result.source_map[0].end_column is not None
    assert python_result.source_map[0].content_hash == python_result.files[0].sha256
    assert sql_result.source_map[0].content_hash == sql_result.files[0].sha256


def test_project_metadata_persists_typed_parameters_and_environment_references():
    metadata = ProjectMetadata(
        name="orders",
        parameters=[Parameter(name="limit", data_type="integer", default=100)],
        environment_references=[EnvironmentReference(name="warehouse", variable="WAREHOUSE_URL")],
    )
    assert metadata.parameters[0].data_type == "integer"
    assert metadata.environment_references[0].variable == "WAREHOUSE_URL"


def test_parameter_and_environment_models_cover_typed_overrides():
    from sdpstudio_core.models import EnvironmentOverride

    parameter = Parameter(name="run_date", data_type="date", required=True)
    secret = Parameter(name="api_key", data_type="secret-ref", default="secret://API_KEY")
    environment = EnvironmentReference(
        name="production",
        variable="SDP_ENV_PRODUCTION",
        overrides=EnvironmentOverride(
            runtime_profile_id="runtime-1",
            catalog="main",
            schema="analytics",
            checkpoint_root="secret://CHECKPOINT_ROOT",
            secret_references={"api": "secret://API_KEY"},
        ),
    )
    assert parameter.data_type == "date"
    assert secret.data_type == "secret-ref"
    assert environment.overrides.runtime_profile_id == "runtime-1"
    assert environment.overrides.secret_references["api"] == "secret://API_KEY"


def test_typed_parameter_validation_rejects_invalid_enum_and_secret_defaults():
    import pytest

    assert Parameter(name="mode", data_type="enum", choices=["full", "incremental"], default="full")
    with pytest.raises(ValueError, match="unique choices"):
        Parameter(name="mode", data_type="enum", choices=["full", "full"])
    with pytest.raises(ValueError, match="secret://"):
        Parameter(name="token", data_type="secret-ref", default="plaintext")


def test_ir_retains_origin_and_source_location_separately_from_canvas_position():
    node = Node(
        id="source",
        type="source.table",
        config={"table": "orders"},
        sourceLocation={"file": "pipeline.py", "start_line": 12, "end_line": 14},
    )
    document = PipelineDocument(nodes=[node])
    ir = lower_pipeline(document).pipeline
    assert ir.nodes[0].source_location is not None
    assert ir.nodes[0].source_location.origin_node_id == "source"
    assert ir.nodes[0].source_location.file == "pipeline.py"
    assert ir.sources[0].origin_node_id == "source"
    assert not hasattr(ir.nodes[0], "position")
