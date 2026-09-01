from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable

from .models import Edge, PipelineDocument, Problem
from .operators import builtin_registry, operator_catalog

# Stable public problem-code registry. Keep these identifiers independent of
# validation traversal order; clients use them for remediation and telemetry.
GRAPH_PROBLEM_CODES = {
    "cycle_detected": "SDPS-GRAPH-001",
    "missing_input": "SDPS-GRAPH-002",
    "invalid_edge": "SDPS-GRAPH-003",
    "unknown_operator": "SDPS-GRAPH-010",
    "unknown_output_port": "SDPS-GRAPH-004",
    "unknown_input_port": "SDPS-GRAPH-005",
    "multiple_input_connections": "SDPS-GRAPH-007",
    "no_declared_output": "SDPS-GRAPH-009",
    "mode_incompatible": "SDPS-GRAPH-011",
}


class GraphIndex:
    def __init__(self, document: PipelineDocument):
        self.document = document
        self.nodes = {n.id: n for n in document.nodes}
        self.incoming: dict[str, list[Edge]] = defaultdict(list)
        self.outgoing: dict[str, list[Edge]] = defaultdict(list)
        for edge in document.edges:
            self.incoming[edge.to.node].append(edge)
            self.outgoing[edge.from_.node].append(edge)

    def topological_order(self) -> list[str]:
        indegree = {node_id: 0 for node_id in self.nodes}
        for edge in self.document.edges:
            if edge.from_.node in self.nodes and edge.to.node in self.nodes:
                indegree[edge.to.node] += 1
        queue = deque(sorted([node_id for node_id, n in indegree.items() if n == 0]))
        order: list[str] = []
        while queue:
            node_id = queue.popleft()
            order.append(node_id)
            for edge in sorted(self.outgoing.get(node_id, []), key=lambda e: e.id):
                indegree[edge.to.node] -= 1
                if indegree[edge.to.node] == 0:
                    queue.append(edge.to.node)
        return order

    def ancestors(self, node_id: str) -> set[str]:
        seen: set[str] = set()
        stack = [node_id]
        while stack:
            current = stack.pop()
            for edge in self.incoming.get(current, []):
                parent = edge.from_.node
                if parent not in seen:
                    seen.add(parent)
                    stack.append(parent)
        return seen

    def descendants(self, node_id: str) -> set[str]:
        """Return every node reachable downstream from ``node_id``."""
        seen: set[str] = set()
        stack = [node_id]
        while stack:
            current = stack.pop()
            for edge in self.outgoing.get(current, []):
                child = edge.to.node
                if child not in seen:
                    seen.add(child)
                    stack.append(child)
        return seen

    def connected_components(self) -> list[set[str]]:
        """Return weakly connected graph components in deterministic order."""
        neighbours: dict[str, set[str]] = {node_id: set() for node_id in self.nodes}
        for edge in self.document.edges:
            if edge.from_.node in neighbours and edge.to.node in neighbours:
                neighbours[edge.from_.node].add(edge.to.node)
                neighbours[edge.to.node].add(edge.from_.node)
        remaining = set(self.nodes)
        components: list[set[str]] = []
        while remaining:
            start = min(remaining)
            component: set[str] = set()
            stack = [start]
            while stack:
                current = stack.pop()
                if current in component:
                    continue
                component.add(current)
                remaining.discard(current)
                stack.extend(sorted(neighbours[current] - component, reverse=True))
            components.append(component)
        return components

    def materialization_boundaries(self) -> set[str]:
        """Return dataset nodes that terminate a generated definition."""
        return {
            node.id
            for node in self.document.nodes
            if node.type.startswith("dataset.") or node.type.startswith("sink.")
        }

    def trace_to_sources(self, node_id: str) -> list[str]:
        ancestors = self.ancestors(node_id)
        order = self.topological_order()
        return [n for n in order if n in ancestors or n == node_id]


def _secret_literal_problems(node) -> list[Problem]:
    problems: list[Problem] = []
    markers = ("password", "token", "secret", "api_key", "apikey", "access_key", "private_key")

    def walk(value, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}.{key}" if path else str(key)
                lower = str(key).lower()
                if (
                    any(marker in lower for marker in markers)
                    and isinstance(child, str)
                    and child
                    and not child.startswith("secret://")
                ):
                    problems.append(
                        Problem(
                            code="SDPS-SEC-001",
                            severity="error",
                            message=f"Potential secret literal detected in {child_path}",
                            node_id=node.id,
                            path=child_path,
                            remediation="Store only a secret reference such as secret://MY_PASSWORD; provide the value through the runtime environment/secret manager.",
                        )
                    )
                else:
                    walk(child, child_path)
        elif isinstance(value, list):
            for i, child in enumerate(value):
                walk(child, f"{path}[{i}]")

    walk(node.config, "config")
    return problems


def validate_graph(document: PipelineDocument) -> list[Problem]:
    problems: list[Problem] = []
    ops = operator_catalog()
    registry = builtin_registry()
    index = GraphIndex(document)

    for node in document.nodes:
        problems.extend(_secret_literal_problems(node))
        op = ops.get(node.type)
        if not op:
            problems.append(
                Problem(
                    code=GRAPH_PROBLEM_CODES["unknown_operator"],
                    severity="error",
                    message=f"Unknown operator: {node.type}",
                    node_id=node.id,
                    remediation="Replace the node with a supported operator or install its plugin.",
                )
            )
            continue
        definition = registry.get(node.type)
        problems.extend(definition.validate_config(node.config, node.id))

    for edge in document.edges:
        if edge.from_.node not in index.nodes:
            problems.append(
                Problem(
                    code=GRAPH_PROBLEM_CODES["invalid_edge"],
                    severity="error",
                    message="Edge source node does not exist",
                    details={"edge": edge.id},
                )
            )
            continue
        if edge.to.node not in index.nodes:
            problems.append(
                Problem(
                    code=GRAPH_PROBLEM_CODES["invalid_edge"],
                    severity="error",
                    message="Edge target node does not exist",
                    details={"edge": edge.id},
                )
            )
            continue
        from_op = ops.get(index.nodes[edge.from_.node].type, {})
        to_op = ops.get(index.nodes[edge.to.node].type, {})
        source_node = index.nodes[edge.from_.node]
        source_streaming = bool(
            source_node.config.get("streaming")
            or source_node.type in {"source.kafka", "dataset.streaming_table"}
        )
        target_modes = set(to_op.get("modes", ["batch", "streaming"]))
        required_mode = "streaming" if source_streaming else "batch"
        if required_mode not in target_modes:
            problems.append(
                Problem(
                    code=GRAPH_PROBLEM_CODES["mode_incompatible"],
                    severity="error",
                    message=f"{required_mode.title()} input is incompatible with {index.nodes[edge.to.node].type}",
                    node_id=edge.to.node,
                    details={"source_mode": required_mode, "target_modes": sorted(target_modes)},
                    remediation="Use an operator supporting the upstream mode or materialize the input at a compatible boundary.",
                )
            )
        if edge.from_.port not in from_op.get("outputs", []):
            problems.append(
                Problem(
                    code=GRAPH_PROBLEM_CODES["unknown_output_port"],
                    severity="error",
                    message=f"Unknown output port {edge.from_.port}",
                    node_id=edge.from_.node,
                )
            )
        if edge.to.port not in to_op.get("inputs", []):
            problems.append(
                Problem(
                    code=GRAPH_PROBLEM_CODES["unknown_input_port"],
                    severity="error",
                    message=f"Unknown input port {edge.to.port}",
                    node_id=edge.to.node,
                )
            )

    for node in document.nodes:
        op = ops.get(node.type)
        if not op:
            continue
        edges = index.incoming.get(node.id, [])
        by_port: dict[str, list[Edge]] = defaultdict(list)
        for e in edges:
            by_port[e.to.port].append(e)
        for port in op.get("inputs", []):
            count = len(by_port.get(port, []))
            port_metadata = op.get("inputPorts", {}).get(port, {})
            optional = (
                bool(port_metadata.get("optional", False))
                if isinstance(port_metadata, dict)
                else False
            )
            cardinality = (
                port_metadata.get("cardinality", "one")
                if isinstance(port_metadata, dict)
                else "one"
            )
            if count == 0:
                if optional:
                    continue
                problems.append(
                    Problem(
                        code=GRAPH_PROBLEM_CODES["missing_input"],
                        severity="error",
                        message=f"Required input '{port}' is not connected",
                        node_id=node.id,
                    )
                )
            elif count > 1 and cardinality != "many":
                problems.append(
                    Problem(
                        code=GRAPH_PROBLEM_CODES["multiple_input_connections"],
                        severity="error",
                        message=f"Input '{port}' has multiple connections",
                        node_id=node.id,
                    )
                )

    if len(index.topological_order()) != len(document.nodes):
        problems.append(
            Problem(
                code=GRAPH_PROBLEM_CODES["cycle_detected"],
                severity="error",
                message="Pipeline contains a cycle",
                remediation="Remove at least one back-edge; SDP dependencies must be acyclic.",
            )
        )

    outputs = [
        n for n in document.nodes if n.type.startswith("dataset.") or n.type.startswith("sink.")
    ]
    if document.nodes and not outputs:
        problems.append(
            Problem(
                code=GRAPH_PROBLEM_CODES["no_declared_output"],
                severity="warning",
                message="Pipeline has no declared output",
                remediation="Add a Materialized View, Streaming Table, Temporary View, or streaming sink.",
            )
        )

    for node in document.nodes:
        if node.type == "transform.join" and node.config.get("how") == "cross":
            problems.append(
                Problem(
                    code="SDPS-PERF-001",
                    severity="warning",
                    message="Cross join can produce a multiplicative data explosion",
                    node_id=node.id,
                    remediation="Prefer an explicit join condition when possible.",
                )
            )
        if node.type == "transform.limit":
            problems.append(
                Problem(
                    code="SDPS-SEM-001",
                    severity="warning",
                    message="Limit changes production dataset semantics",
                    node_id=node.id,
                    remediation="Use Limit primarily for debugging or make the row cap an explicit business requirement.",
                )
            )
        if node.type == "transform.repartition":
            problems.append(
                Problem(
                    code="SDPS-PERF-002",
                    severity="warning",
                    message="Explicit repartition can force a shuffle",
                    node_id=node.id,
                    remediation="Verify partition count/keys with the Spark plan and stage metrics.",
                )
            )

    return problems


def has_errors(problems: Iterable[Problem]) -> bool:
    return any(p.severity == "error" for p in problems)
