"""Provider-neutral intermediate representation for pipeline compilation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .graph import GraphIndex, validate_graph
from .models import Edge, Node, PipelineDocument, Problem


@dataclass(frozen=True)
class IRExpression:
    text: str
    origin_node_id: str | None = None
    language: Literal["python", "sql", "literal"] = "literal"


@dataclass(frozen=True)
class IRParameterRef:
    name: str
    origin_node_id: str | None = None


@dataclass(frozen=True)
class IRSecretRef:
    name: str
    origin_node_id: str | None = None


@dataclass(frozen=True)
class IRSourceLocation:
    """Stable source provenance kept separate from visual canvas coordinates."""

    file: str | None = None
    start_line: int | None = None
    start_column: int | None = None
    end_line: int | None = None
    end_column: int | None = None
    origin_node_id: str | None = None


@dataclass(frozen=True)
class IRSource:
    id: str
    operator: str
    config: tuple[tuple[str, Any], ...]
    mode: Literal["batch", "streaming"]
    expression: IRExpression | None = None
    origin_node_id: str | None = None
    source_location: IRSourceLocation | None = None


@dataclass(frozen=True)
class IRTransform:
    id: str
    operator: str
    config: tuple[tuple[str, Any], ...]
    mode: Literal["batch", "streaming"]
    expression: IRExpression | None = None
    origin_node_id: str | None = None
    source_location: IRSourceLocation | None = None


@dataclass(frozen=True)
class IRSink:
    id: str
    operator: str
    name: str
    config: tuple[tuple[str, Any], ...]
    mode: Literal["batch", "streaming"]
    expression: IRExpression | None = None
    origin_node_id: str | None = None
    source_location: IRSourceLocation | None = None


@dataclass(frozen=True)
class IRFlow:
    id: str
    from_node: str
    from_port: str
    to_node: str
    to_port: str
    source_location: IRSourceLocation | None = None


@dataclass(frozen=True)
class IRNode:
    id: str
    operator: str
    config: tuple[tuple[str, Any], ...]
    mode: Literal["batch", "streaming"]
    kind: Literal["source", "transform", "sink"]
    expression: IRExpression | None = None
    source_location: IRSourceLocation | None = None


@dataclass(frozen=True)
class IRDataset:
    name: str
    kind: str
    mode: Literal["batch", "streaming"]
    origin_node_id: str
    expression: IRExpression | None = None


@dataclass(frozen=True)
class IRPipeline:
    name: str
    nodes: tuple[IRNode, ...] = ()
    flows: tuple[IRFlow, ...] = ()
    datasets: tuple[IRDataset, ...] = ()
    sources: tuple[IRSource, ...] = ()
    transforms: tuple[IRTransform, ...] = ()
    sinks: tuple[IRSink, ...] = ()
    parameters: tuple[IRParameterRef, ...] = ()
    secrets: tuple[IRSecretRef, ...] = ()
    origin_pipeline_id: str | None = None

    def graph_view(self) -> Any:
        """Return a semantic graph view for backends without re-lowering to a document.

        The view intentionally contains only compiler-owned fields (operator, config,
        topology and origin metadata). Canvas coordinates are not part of this view.
        """
        nodes = [
            IRGraphNode(id=node.id, type=node.operator, config=_thaw(node.config))
            for node in self.nodes
        ]
        edges = [
            Edge.model_validate(
                {
                    "id": flow.id,
                    "from": {"node": flow.from_node, "port": flow.from_port},
                    "to": {"node": flow.to_node, "port": flow.to_port},
                }
            )
            for flow in self.flows
        ]
        return _IRGraphView(self.name, nodes, edges, self.origin_pipeline_id or "ir-pipeline", self)


@dataclass(frozen=True)
class _IRGraphView:
    name: str
    nodes: list[IRGraphNode]
    edges: list[Edge]
    pipelineId: str = "ir-pipeline"
    source_ir: IRPipeline | None = None


@dataclass(frozen=True)
class IRGraphNode:
    """Minimal semantic graph node exposed to compiler passes; no UI fields."""

    id: str
    type: str
    config: dict[str, Any]
    model_extra: dict[str, Any] | None = None


@dataclass(frozen=True)
class IRProject:
    name: str
    pipelines: tuple[IRPipeline, ...] = ()


@dataclass(frozen=True)
class IRLoweringResult:
    pipeline: IRPipeline
    problems: tuple[Problem, ...] = ()


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return (
            "__dict__",
            tuple((str(key), _freeze(value[key])) for key in sorted(value, key=str)),
        )
    if isinstance(value, list):
        return ("__list__", tuple(_freeze(item) for item in value))
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, tuple):
        if len(value) == 2 and value[0] == "__dict__":
            return {str(key): _thaw(child) for key, child in value[1]}
        if len(value) == 2 and value[0] == "__list__":
            return [_thaw(child) for child in value[1]]
    return value


def _collect_refs(value: Any, parameters: set[str], secrets: set[str]) -> None:
    if isinstance(value, str):
        if value.startswith("secret://"):
            secrets.add(value.removeprefix("secret://").strip())
        elif value.startswith("parameter://"):
            parameters.add(value.removeprefix("parameter://").strip())
    elif isinstance(value, dict):
        for child in value.values():
            _collect_refs(child, parameters, secrets)
    elif isinstance(value, list):
        for child in value:
            _collect_refs(child, parameters, secrets)


def _expression_for(node: Node) -> IRExpression | None:
    for key in ("expression", "query", "condition"):
        value = node.config.get(key)
        if isinstance(value, str) and value.strip():
            language: Literal["python", "sql", "literal"] = (
                "sql" if "sql" in node.type else "literal"
            )
            return IRExpression(value, node.id, language)
    return None


def _source_location_for(node: Node) -> IRSourceLocation:
    raw = node.model_extra or {}
    location = raw.get("sourceLocation") or raw.get("source_location") or {}
    return IRSourceLocation(
        file=location.get("file") if isinstance(location, dict) else None,
        start_line=location.get("start_line") if isinstance(location, dict) else None,
        start_column=location.get("start_column") if isinstance(location, dict) else None,
        end_line=location.get("end_line") if isinstance(location, dict) else None,
        end_column=location.get("end_column") if isinstance(location, dict) else None,
        origin_node_id=node.id,
    )


def lower_pipeline(document: PipelineDocument) -> IRLoweringResult:
    """Resolve graph order, names, references, and execution mode into immutable IR."""
    if isinstance(document, _IRGraphView) and document.source_ir is not None:
        return IRLoweringResult(document.source_ir, tuple(validate_graph(document)))
    problems = tuple(validate_graph(document))
    index = GraphIndex(document)
    nodes_by_id = {node.id: node for node in document.nodes}
    order = index.topological_order()
    modes: dict[str, Literal["batch", "streaming"]] = {}
    for node_id in order:
        node = nodes_by_id[node_id]
        if node.type.startswith("source."):
            modes[node_id] = (
                "streaming"
                if node.type == "source.kafka" or bool(node.config.get("streaming"))
                else "batch"
            )
        else:
            modes[node_id] = (
                "streaming"
                if any(
                    modes.get(edge.from_.node) == "streaming" for edge in index.incoming[node_id]
                )
                else "batch"
            )
    parameters: set[str] = set()
    secrets: set[str] = set()
    ir_nodes: list[IRNode] = []
    sources: list[IRSource] = []
    transforms: list[IRTransform] = []
    sinks: list[IRSink] = []
    datasets: list[IRDataset] = []
    for node_id in order:
        node = nodes_by_id[node_id]
        config = _freeze(node.config)
        _collect_refs(node.config, parameters, secrets)
        expression = _expression_for(node)
        source_location = _source_location_for(node)
        mode = modes.get(node.id, "batch")
        if node.type.startswith("source."):
            kind: Literal["source", "transform", "sink"] = "source"
            sources.append(
                IRSource(node.id, node.type, config, mode, expression, node.id, source_location)
            )
        elif node.type.startswith("dataset.") or node.type.startswith("sink."):
            kind = "sink"
            name = str(node.config.get("name") or node.config.get("table") or node.id)
            sinks.append(
                IRSink(node.id, node.type, name, config, mode, expression, node.id, source_location)
            )
            datasets.append(
                IRDataset(name, node.type.removeprefix("dataset."), mode, node.id, expression)
            )
        else:
            kind = "transform"
            transforms.append(
                IRTransform(node.id, node.type, config, mode, expression, node.id, source_location)
            )
        ir_nodes.append(
            IRNode(
                node.id,
                node.type,
                config,
                mode,
                kind,
                expression,
                source_location,
            )
        )
    flows = tuple(
        IRFlow(edge.id, edge.from_.node, edge.from_.port, edge.to.node, edge.to.port)
        for edge in sorted(document.edges, key=lambda item: item.id)
    )
    pipeline = IRPipeline(
        name=document.name,
        nodes=tuple(ir_nodes),
        flows=flows,
        datasets=tuple(datasets),
        sources=tuple(sources),
        transforms=tuple(transforms),
        sinks=tuple(sinks),
        parameters=tuple(IRParameterRef(name) for name in sorted(parameters) if name),
        secrets=tuple(IRSecretRef(name) for name in sorted(secrets) if name),
        origin_pipeline_id=document.pipelineId,
    )
    return IRLoweringResult(pipeline, problems)


def pipeline_to_ir(document: PipelineDocument) -> IRPipeline:
    """Compatibility wrapper returning the normalized pipeline IR."""
    return lower_pipeline(document).pipeline
