from __future__ import annotations

from .models import PipelineDocument, Problem, RuntimeCapabilities
from .operators import builtin_registry


def validate_capabilities(
    document: PipelineDocument, capabilities: RuntimeCapabilities
) -> list[Problem]:
    required: set[str] = set()
    registry = builtin_registry()
    problems: list[Problem] = []
    for node in document.nodes:
        try:
            definition = registry.get(node.type)
        except KeyError:
            definition = None
        if definition:
            required.update(definition.required_capabilities)
            for capability in sorted(definition.forbidden_capabilities):
                if getattr(capabilities, capability, False):
                    problems.append(
                        Problem(
                            code="SDPS-CAP-003",
                            severity="warning",
                            message=f"Runtime capability is discouraged for {node.type}: {capability}",
                            node_id=node.id,
                            remediation="Use a portable capability or an approved downgrade.",
                        )
                    )
        if node.type.startswith("dataset."):
            required.add(node.type.removeprefix("dataset."))
        if node.type == "sink.external":
            required.add("sink")
        if node.type == "source.kafka" or node.config.get("streaming"):
            required.add("streaming_table")
    for capability in sorted(required):
        if not getattr(capabilities, capability, False):
            downgrade = capabilities.downgrade_map.get(capability)
            problems.append(
                Problem(
                    code="SDPS-CAP-002" if downgrade else "SDPS-CAP-001",
                    severity="warning" if downgrade else "error",
                    message=(
                        f"Runtime lacks capability: {capability}; downgrade available: {downgrade}"
                        if downgrade
                        else f"Runtime lacks capability: {capability}"
                    ),
                    remediation=(
                        f"Apply the documented downgrade: {downgrade}."
                        if downgrade
                        else "Select a compatible runtime profile or change the pipeline."
                    ),
                )
            )
    return problems
