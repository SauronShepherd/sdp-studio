from pathlib import Path

import yaml
from sdpstudio_core.graph import validate_graph
from sdpstudio_core.models import PipelineDocument
from sdpstudio_core.quality_suite import load_quality_suite

ROOT = Path(__file__).parents[1]


def test_retail_example_has_join_and_aggregation_acceptance_shape():
    project = ROOT / "examples" / "retail-etl"
    document = PipelineDocument.model_validate(
        yaml.safe_load(
            (project / ".sdpstudio" / "pipelines" / "main.sdpstudio.yaml").read_text(
                encoding="utf-8"
            )
        )
    )
    problems = validate_graph(document)
    assert not [problem for problem in problems if problem.severity == "error"]
    assert any(node.type == "transform.join" for node in document.nodes)
    assert any(node.type == "transform.aggregate" for node in document.nodes)
    customer_sources = [
        node
        for node in document.nodes
        if node.type == "source.file" and node.config.get("path") == "data/customers.csv"
    ]
    assert customer_sources and (project / "data" / "customers.csv").exists()


def test_cdc_example_is_a_visual_pipeline_with_quality_suite():
    project = ROOT / "examples" / "cdc-auto-scd1"
    document = PipelineDocument.model_validate(
        yaml.safe_load(
            (project / ".sdpstudio" / "pipelines" / "main.sdpstudio.yaml").read_text(
                encoding="utf-8"
            )
        )
    )
    assert not [problem for problem in validate_graph(document) if problem.severity == "error"]
    assert any(node.type == "dataset.auto_cdc_scd1" for node in document.nodes)
    suite = load_quality_suite(project / ".sdpstudio" / "tests" / "quality.yaml")
    assert suite[0]["mode"] == "post-run"


def test_streaming_kafka_example_is_openable_and_has_streaming_sink_flow():
    project = ROOT / "examples" / "streaming-kafka"
    document = PipelineDocument.model_validate(
        yaml.safe_load(
            (project / ".sdpstudio" / "pipelines" / "main.sdpstudio.yaml").read_text(
                encoding="utf-8"
            )
        )
    )
    problems = validate_graph(document)
    assert not [problem for problem in problems if problem.severity == "error"]
    assert any(node.type == "source.kafka" for node in document.nodes)
    assert any(node.type == "sink.external" for node in document.nodes)
    assert any(
        node.config.get("streaming") is True
        for node in document.nodes
        if node.type == "source.kafka"
    )
