from __future__ import annotations

from dataclasses import dataclass, field
from importlib import metadata
from typing import Any

from .models import Problem
from .plugin_contract import validate_plugin_manifest

BUILTIN_OPERATORS: list[dict[str, Any]] = [
    {
        "id": "source.table",
        "title": "Table",
        "category": "Sources",
        "inputs": [],
        "outputs": ["out"],
        "modes": ["batch", "streaming"],
        "fields": [
            {
                "name": "table",
                "label": "Table",
                "type": "text",
                "required": True,
                "placeholder": "catalog.schema.table",
            },
            {"name": "streaming", "label": "Streaming", "type": "boolean", "default": False},
        ],
    },
    {
        "id": "source.file",
        "title": "File",
        "category": "Sources",
        "inputs": [],
        "outputs": ["out"],
        "modes": ["batch", "streaming"],
        "fields": [
            {"name": "path", "label": "Path", "type": "text", "required": True},
            {
                "name": "format",
                "label": "Format",
                "type": "enum",
                "options": ["parquet", "csv", "json", "orc", "text"],
                "default": "parquet",
            },
            {"name": "streaming", "label": "Streaming", "type": "boolean", "default": False},
            {"name": "options", "label": "Options (JSON)", "type": "json", "default": {}},
        ],
    },
    {
        "id": "source.jdbc",
        "title": "JDBC",
        "category": "Sources",
        "inputs": [],
        "outputs": ["out"],
        "modes": ["batch"],
        "fields": [
            {"name": "url", "label": "JDBC URL", "type": "text", "required": True},
            {"name": "dbtable", "label": "Table / subquery", "type": "text", "required": True},
            {"name": "options", "label": "Options (JSON)", "type": "json", "default": {}},
        ],
    },
    {
        "id": "source.kafka",
        "title": "Kafka Stream",
        "category": "Sources",
        "inputs": [],
        "outputs": ["out"],
        "modes": ["streaming"],
        "fields": [
            {
                "name": "bootstrapServers",
                "label": "Bootstrap servers",
                "type": "text",
                "required": True,
            },
            {"name": "subscribe", "label": "Topic", "type": "text", "required": True},
            {"name": "options", "label": "Options (JSON)", "type": "json", "default": {}},
        ],
    },
    {
        "id": "source.sql_query",
        "title": "SQL Query",
        "category": "Sources",
        "inputs": [],
        "outputs": ["out"],
        "modes": ["batch"],
        "fields": [{"name": "query", "label": "Spark SQL", "type": "code", "required": True}],
    },
    {
        "id": "source.dataset_reference",
        "title": "Pipeline Dataset Reference",
        "category": "Sources",
        "inputs": [],
        "outputs": ["out"],
        "modes": ["batch", "streaming"],
        "fields": [
            {"name": "name", "label": "Dataset name", "type": "text", "required": True},
            {"name": "streaming", "label": "Streaming", "type": "boolean", "default": False},
        ],
    },
    {
        "id": "source.generic",
        "title": "DataSource V2",
        "category": "Sources",
        "inputs": [],
        "outputs": ["out"],
        "modes": ["batch", "streaming"],
        "fields": [
            {"name": "format", "label": "Provider format", "type": "text", "required": True},
            {"name": "options", "label": "Options (JSON)", "type": "json", "default": {}},
            {"name": "streaming", "label": "Streaming", "type": "boolean", "default": False},
        ],
    },
    {
        "id": "source.custom_pyspark",
        "title": "Custom PySpark Source",
        "category": "Sources",
        "inputs": [],
        "outputs": ["out"],
        "modes": ["batch", "streaming"],
        "codeTargets": ["python"],
        "fields": [
            {"name": "code", "label": "PySpark expression", "type": "code", "required": True}
        ],
    },
    {
        "id": "utility.parameter",
        "title": "Parameter",
        "category": "Utility",
        "inputs": [],
        "outputs": ["out"],
        "fields": [
            {"name": "name", "label": "Parameter name", "type": "text", "required": True},
            {"name": "default", "label": "Default value", "type": "text"},
        ],
    },
    {
        "id": "utility.constant",
        "title": "Constant",
        "category": "Utility",
        "inputs": [],
        "outputs": ["out"],
        "fields": [
            {"name": "name", "label": "Output column", "type": "text", "required": True},
            {"name": "value", "label": "Value", "type": "text", "required": True},
        ],
    },
    {
        "id": "utility.note",
        "title": "Note",
        "category": "Utility",
        "inputs": [],
        "outputs": [],
        "fields": [{"name": "markdown", "label": "Markdown", "type": "text"}],
    },
    {
        "id": "utility.group",
        "title": "Group / Subflow",
        "category": "Utility",
        "inputs": ["in"],
        "outputs": ["out"],
        "fields": [{"name": "name", "label": "Group name", "type": "text", "required": True}],
    },
    {
        "id": "utility.component_input",
        "title": "Reusable Component Input",
        "category": "Utility",
        "inputs": [],
        "outputs": ["out"],
        "fields": [{"name": "name", "label": "Input name", "type": "text", "required": True}],
    },
    {
        "id": "utility.component_output",
        "title": "Reusable Component Output",
        "category": "Utility",
        "inputs": ["in"],
        "outputs": [],
        "fields": [{"name": "name", "label": "Output name", "type": "text", "required": True}],
    },
    {
        "id": "utility.custom_code",
        "title": "Custom Code",
        "category": "Utility",
        "inputs": ["in"],
        "outputs": ["out"],
        "codeTargets": ["python", "sql"],
        "fields": [{"name": "code", "label": "Code", "type": "code", "required": True}],
    },
    {
        "id": "transform.filter",
        "title": "Filter",
        "category": "Transforms",
        "inputs": ["in"],
        "outputs": ["out"],
        "fields": [
            {
                "name": "expression",
                "label": "SQL expression",
                "type": "code",
                "required": True,
                "placeholder": "status = 'COMPLETE'",
            }
        ],
    },
    {
        "id": "transform.select",
        "title": "Select",
        "category": "Transforms",
        "inputs": ["in"],
        "outputs": ["out"],
        "fields": [
            {
                "name": "columns",
                "label": "Columns / expressions",
                "type": "list",
                "required": True,
                "default": ["*"],
            }
        ],
    },
    {
        "id": "transform.derive",
        "title": "Derive Column",
        "category": "Transforms",
        "inputs": ["in"],
        "outputs": ["out"],
        "fields": [
            {"name": "name", "label": "Column name", "type": "text", "required": True},
            {"name": "expression", "label": "SQL expression", "type": "code", "required": True},
        ],
    },
    {
        "id": "transform.sql_project",
        "title": "SQL Transform Block",
        "category": "Transforms",
        "inputs": ["in"],
        "outputs": ["out"],
        "codeTargets": ["python", "sql"],
        "fields": [{"name": "query", "label": "SQL projection", "type": "code", "required": True}],
    },
    {
        "id": "transform.pyspark_block",
        "title": "PySpark Transform Block",
        "category": "Transforms",
        "inputs": ["in"],
        "outputs": ["out"],
        "codeTargets": ["python"],
        "fields": [
            {"name": "code", "label": "PySpark expression", "type": "code", "required": True}
        ],
    },
    {
        "id": "transform.drop",
        "title": "Drop Columns",
        "category": "Transforms",
        "inputs": ["in"],
        "outputs": ["out"],
        "fields": [{"name": "columns", "label": "Columns", "type": "list", "required": True}],
    },
    {
        "id": "transform.rename",
        "title": "Rename Columns",
        "category": "Transforms",
        "inputs": ["in"],
        "outputs": ["out"],
        "fields": [
            {
                "name": "mapping",
                "label": "Mapping (JSON)",
                "type": "json",
                "required": True,
                "default": {},
            }
        ],
    },
    {
        "id": "transform.cast",
        "title": "Cast Column",
        "category": "Transforms",
        "inputs": ["in"],
        "outputs": ["out"],
        "fields": [
            {"name": "column", "label": "Column", "type": "text", "required": True},
            {
                "name": "dataType",
                "label": "Spark SQL type",
                "type": "text",
                "required": True,
                "placeholder": "decimal(18,2)",
            },
        ],
    },
    {
        "id": "transform.fill_nulls",
        "title": "Fill Nulls",
        "category": "Transforms",
        "inputs": ["in"],
        "outputs": ["out"],
        "fields": [
            {
                "name": "values",
                "label": "Values by column (JSON)",
                "type": "json",
                "required": True,
                "default": {},
            }
        ],
    },
    {
        "id": "transform.drop_nulls",
        "title": "Drop Nulls",
        "category": "Transforms",
        "inputs": ["in"],
        "outputs": ["out"],
        "fields": [
            {
                "name": "how",
                "label": "How",
                "type": "enum",
                "options": ["any", "all"],
                "default": "any",
            },
            {"name": "subset", "label": "Subset", "type": "list", "default": []},
        ],
    },
    {
        "id": "transform.drop_duplicates",
        "title": "Drop Duplicates",
        "category": "Transforms",
        "inputs": ["in"],
        "outputs": ["out"],
        "fields": [{"name": "columns", "label": "Key columns", "type": "list", "default": []}],
    },
    {
        "id": "transform.deduplicate_event_time",
        "title": "Deduplicate with Event Time",
        "category": "Transforms",
        "inputs": ["in"],
        "outputs": ["out"],
        "modes": ["batch", "streaming"],
        "fields": [
            {"name": "columns", "label": "Key columns", "type": "list", "required": True},
            {"name": "eventTime", "label": "Event-time column", "type": "text", "required": True},
            {
                "name": "watermark",
                "label": "Watermark delay",
                "type": "text",
                "default": "10 minutes",
            },
        ],
    },
    {
        "id": "transform.union_by_name",
        "title": "Union By Name",
        "category": "Transforms",
        "inputs": ["left", "right"],
        "outputs": ["out"],
        "fields": [
            {
                "name": "allowMissingColumns",
                "label": "Allow missing columns",
                "type": "boolean",
                "default": False,
            }
        ],
    },
    {
        "id": "transform.sort",
        "title": "Sort / Order",
        "category": "Transforms",
        "inputs": ["in"],
        "outputs": ["out"],
        "fields": [
            {"name": "expressions", "label": "Sort expressions", "type": "list", "required": True}
        ],
    },
    {
        "id": "transform.limit",
        "title": "Limit",
        "category": "Transforms",
        "inputs": ["in"],
        "outputs": ["out"],
        "fields": [
            {"name": "count", "label": "Rows", "type": "number", "required": True, "default": 100}
        ],
    },
    {
        "id": "transform.explode",
        "title": "Explode",
        "category": "Transforms",
        "inputs": ["in"],
        "outputs": ["out"],
        "fields": [
            {"name": "column", "label": "Array / map column", "type": "text", "required": True},
            {"name": "target", "label": "Output column", "type": "text", "required": True},
        ],
    },
    {
        "id": "transform.posexplode",
        "title": "Position Explode",
        "category": "Transforms",
        "inputs": ["in"],
        "outputs": ["out"],
        "fields": [
            {"name": "column", "label": "Array / map column", "type": "text", "required": True},
            {"name": "position", "label": "Position output", "type": "text", "default": "pos"},
            {"name": "target", "label": "Value output", "type": "text", "required": True},
        ],
    },
    {
        "id": "transform.repartition",
        "title": "Repartition",
        "category": "Performance",
        "inputs": ["in"],
        "outputs": ["out"],
        "fields": [
            {
                "name": "partitions",
                "label": "Partitions",
                "type": "number",
                "required": True,
                "default": 200,
            },
            {"name": "columns", "label": "Partition columns", "type": "list", "default": []},
        ],
    },
    {
        "id": "transform.coalesce",
        "title": "Coalesce",
        "category": "Performance",
        "inputs": ["in"],
        "outputs": ["out"],
        "fields": [
            {
                "name": "partitions",
                "label": "Partitions",
                "type": "number",
                "required": True,
                "default": 1,
            }
        ],
    },
    {
        "id": "transform.aggregate",
        "title": "Aggregate",
        "category": "Transforms",
        "inputs": ["in"],
        "outputs": ["out"],
        "fields": [
            {"name": "groupBy", "label": "Group by", "type": "list", "default": []},
            {
                "name": "aggregations",
                "label": "Aggregations",
                "type": "json",
                "default": [{"expression": "count(*)", "alias": "row_count"}],
            },
        ],
    },
    {
        "id": "transform.join",
        "title": "Join",
        "category": "Transforms",
        "inputs": ["left", "right"],
        "outputs": ["out"],
        "fields": [
            {
                "name": "how",
                "label": "Join type",
                "type": "enum",
                "options": ["inner", "left", "right", "full", "left_semi", "left_anti", "cross"],
                "default": "inner",
            },
            {
                "name": "condition",
                "label": "Condition",
                "type": "code",
                "required": False,
                "placeholder": "left.id = right.id",
            },
        ],
    },
    {
        "id": "transform.distinct",
        "title": "Distinct",
        "category": "Transforms",
        "inputs": ["in"],
        "outputs": ["out"],
        "fields": [],
    },
    {
        "id": "transform.reorder",
        "title": "Reorder Columns",
        "category": "Transforms",
        "inputs": ["in"],
        "outputs": ["out"],
        "fields": [{"name": "columns", "label": "Column order", "type": "list", "required": True}],
    },
    {
        "id": "transform.replace",
        "title": "Replace Values",
        "category": "Transforms",
        "inputs": ["in"],
        "outputs": ["out"],
        "fields": [
            {"name": "column", "label": "Column", "type": "text", "required": True},
            {"name": "mapping", "label": "Mapping (JSON)", "type": "json", "required": True},
        ],
    },
    {
        "id": "transform.intersect",
        "title": "Intersect",
        "category": "Transforms",
        "inputs": ["left", "right"],
        "outputs": ["out"],
        "fields": [],
    },
    {
        "id": "transform.except",
        "title": "Except",
        "category": "Transforms",
        "inputs": ["left", "right"],
        "outputs": ["out"],
        "fields": [],
    },
    {
        "id": "transform.flatten_struct",
        "title": "Flatten Struct",
        "category": "Transforms",
        "inputs": ["in"],
        "outputs": ["out"],
        "fields": [{"name": "column", "label": "Struct column", "type": "text", "required": True}],
    },
    {
        "id": "transform.build_struct",
        "title": "Build Struct",
        "category": "Transforms",
        "inputs": ["in"],
        "outputs": ["out"],
        "fields": [
            {"name": "target", "label": "Target column", "type": "text", "required": True},
            {"name": "fields", "label": "Fields (JSON)", "type": "json", "required": True},
        ],
    },
    {
        "id": "transform.build_map",
        "title": "Build Map",
        "category": "Transforms",
        "inputs": ["in"],
        "outputs": ["out"],
        "fields": [
            {"name": "target", "label": "Target column", "type": "text", "required": True},
            {"name": "keys", "label": "Key expressions", "type": "list", "required": True},
            {"name": "values", "label": "Value expressions", "type": "list", "required": True},
        ],
    },
    {
        "id": "transform.build_array",
        "title": "Build Array",
        "category": "Transforms",
        "inputs": ["in"],
        "outputs": ["out"],
        "fields": [
            {"name": "target", "label": "Target column", "type": "text", "required": True},
            {"name": "expressions", "label": "Expressions", "type": "list", "required": True},
        ],
    },
    {
        "id": "transform.watermark",
        "title": "Watermark",
        "category": "Streaming",
        "inputs": ["in"],
        "outputs": ["out"],
        "fields": [
            {"name": "column", "label": "Event-time column", "type": "text", "required": True},
            {
                "name": "delay",
                "label": "Delay",
                "type": "text",
                "required": True,
                "placeholder": "10 minutes",
            },
        ],
    },
    {
        "id": "transform.json_parse",
        "title": "Parse JSON",
        "category": "Transforms",
        "inputs": ["in"],
        "outputs": ["out"],
        "fields": [
            {"name": "column", "label": "JSON column", "type": "text", "required": True},
            {"name": "schema", "label": "Schema DDL", "type": "text", "required": True},
            {"name": "target", "label": "Target column", "type": "text", "required": True},
        ],
    },
    {
        "id": "transform.window",
        "title": "Window Expression",
        "category": "Transforms",
        "inputs": ["in"],
        "outputs": ["out"],
        "fields": [
            {"name": "target", "label": "Target column", "type": "text", "required": True},
            {
                "name": "expression",
                "label": "Spark SQL expression",
                "type": "code",
                "required": True,
            },
            {"name": "partitionBy", "label": "Partition columns", "type": "list", "default": []},
            {"name": "orderBy", "label": "Order columns", "type": "list", "default": []},
        ],
    },
    {
        "id": "quality.column_rule",
        "title": "Column Rule",
        "category": "Quality",
        "inputs": ["in"],
        "outputs": ["out"],
        "fields": [
            {"name": "column", "label": "Column", "type": "text", "required": True},
            {"name": "condition", "label": "Rule expression", "type": "code", "required": True},
            {
                "name": "action",
                "label": "Failure action",
                "type": "enum",
                "options": ["warn", "drop", "fail"],
                "default": "warn",
            },
        ],
    },
    {
        "id": "quality.null_rate",
        "title": "Null-Rate Rule",
        "category": "Quality",
        "inputs": ["in"],
        "outputs": ["out"],
        "fields": [
            {"name": "column", "label": "Column", "type": "text", "required": True},
            {"name": "maxRate", "label": "Maximum null rate", "type": "number", "required": True},
        ],
    },
    {
        "id": "quality.uniqueness",
        "title": "Uniqueness Rule",
        "category": "Quality",
        "inputs": ["in"],
        "outputs": ["out"],
        "fields": [{"name": "columns", "label": "Key columns", "type": "list", "required": True}],
    },
    {
        "id": "quality.schema_contract",
        "title": "Schema Contract",
        "category": "Quality",
        "inputs": ["in"],
        "outputs": ["out"],
        "fields": [
            {"name": "schema", "label": "Expected schema JSON", "type": "json", "required": True}
        ],
    },
    {
        "id": "quality.profile_probe",
        "title": "Profile Probe",
        "category": "Quality",
        "inputs": ["in"],
        "outputs": ["out"],
        "fields": [
            {"name": "columns", "label": "Columns to profile", "type": "list", "default": []}
        ],
    },
    {
        "id": "quality.row_count_range",
        "title": "Row Count Range",
        "category": "Quality",
        "inputs": ["in"],
        "outputs": ["out"],
        "fields": [
            {"name": "minimum", "label": "Minimum rows", "type": "number", "default": 0},
            {"name": "maximum", "label": "Maximum rows", "type": "number"},
            {
                "name": "action",
                "label": "Failure action",
                "type": "enum",
                "options": ["warn", "fail"],
                "default": "warn",
            },
        ],
    },
    {
        "id": "quality.referential_sample",
        "title": "Referential Sample Test",
        "category": "Quality",
        "inputs": ["in", "reference"],
        "inputPorts": {"reference": {"optional": True}},
        "outputs": ["out"],
        "fields": [
            {"name": "columns", "label": "Key columns", "type": "list", "required": True},
            {
                "name": "sampleFraction",
                "label": "Sample fraction",
                "type": "number",
                "default": 0.1,
            },
            {
                "name": "action",
                "label": "Failure action",
                "type": "enum",
                "options": ["warn", "fail"],
                "default": "warn",
            },
        ],
    },
    {
        "id": "quality.quarantine_split",
        "title": "Quarantine Split",
        "category": "Quality",
        "inputs": ["in"],
        "outputs": ["accepted", "quarantine"],
        "outputPorts": {"accepted": {"cardinality": "one"}, "quarantine": {"cardinality": "one"}},
        "fields": [
            {
                "name": "condition",
                "label": "Acceptance condition",
                "type": "code",
                "required": True,
            },
            {
                "name": "quarantineName",
                "label": "Quarantine dataset",
                "type": "text",
                "required": True,
            },
        ],
    },
    {
        "id": "dataset.materialized_view",
        "title": "Materialized View",
        "category": "Outputs",
        "inputs": ["in"],
        "outputs": ["out"],
        "fields": [{"name": "name", "label": "Dataset name", "type": "text", "required": True}],
    },
    {
        "id": "dataset.streaming_table",
        "title": "Streaming Table",
        "category": "Outputs",
        "inputs": ["in"],
        "outputs": ["out"],
        "fields": [{"name": "name", "label": "Dataset name", "type": "text", "required": True}],
    },
    {
        "id": "dataset.temporary_view",
        "title": "Temporary View",
        "category": "Outputs",
        "inputs": ["in"],
        "outputs": ["out"],
        "fields": [{"name": "name", "label": "View name", "type": "text", "required": True}],
    },
    {
        "id": "dataset.auto_cdc_scd1",
        "title": "Auto CDC · SCD Type 1",
        "category": "Outputs",
        "inputs": ["in"],
        "outputs": ["out"],
        "modes": ["streaming"],
        "fields": [
            {"name": "name", "label": "Target name", "type": "text", "required": True},
            {"name": "keys", "label": "Key columns", "type": "list", "required": True},
            {"name": "sequence_by", "label": "Sequence column", "type": "text", "required": True},
            {"name": "apply_as_deletes", "label": "Delete condition", "type": "code"},
        ],
    },
    {
        "id": "sink.external",
        "title": "Streaming Sink",
        "category": "Outputs",
        "inputs": ["in"],
        "outputs": [],
        "modes": ["streaming"],
        "fields": [
            {"name": "name", "label": "Sink name", "type": "text", "required": True},
            {
                "name": "format",
                "label": "Format",
                "type": "text",
                "required": True,
                "placeholder": "kafka",
            },
            {"name": "options", "label": "Options (JSON)", "type": "json", "default": {}},
        ],
    },
]


PLUGIN_GROUP = "sdpstudio.operator_definitions"


def discover_operator_plugins() -> list[dict[str, Any]]:
    """Load optional operator definitions without making plugins core dependencies."""
    try:
        entries: Any = metadata.entry_points()
        selected = (
            entries.select(group=PLUGIN_GROUP)
            if hasattr(entries, "select")
            else entries.get(PLUGIN_GROUP, [])
        )
    except Exception:
        return []
    builtin_ids = {item["id"] for item in BUILTIN_OPERATORS}
    discovered: list[dict[str, Any]] = []
    for entry in selected:
        try:
            loaded = entry.load()()
            values = loaded if isinstance(loaded, list) else [loaded]
            for item in values:
                if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                    continue
                if not validate_plugin_manifest(item, identifier=str(item.get("id"))):
                    continue
                if item["id"] in builtin_ids or not isinstance(item.get("title"), str):
                    continue
                if not isinstance(item.get("inputs", []), list) or not isinstance(
                    item.get("outputs", []), list
                ):
                    continue
                discovered.append(item)
        except Exception:
            continue
    return discovered


def operator_catalog() -> dict[str, dict[str, Any]]:
    return {op["id"]: op for op in [*BUILTIN_OPERATORS, *discover_operator_plugins()]}


@dataclass(frozen=True)
class PortDefinition:
    name: str
    data_kind: str = "dataframe"
    cardinality: str = "one"
    optional: bool = False


@dataclass(frozen=True)
class OperatorDefinition:
    id: str
    version: int
    title: str
    category: str
    inputs: tuple[PortDefinition, ...]
    outputs: tuple[PortDefinition, ...]
    modes: frozenset[str] = frozenset({"batch", "streaming"})
    code_targets: frozenset[str] = frozenset({"python"})
    required_capabilities: frozenset[str] = frozenset()
    forbidden_capabilities: frozenset[str] = frozenset()
    config_schema: dict[str, Any] = field(default_factory=dict)
    ui_schema: dict[str, Any] = field(default_factory=dict)
    validator_hook: str | None = None
    compiler_hook: str | None = None
    schema_inference_hook: str | None = None
    preview_hook: str | None = None
    documentation_key: str | None = None

    def contract_metadata(self) -> dict[str, Any]:
        """Return deterministic, provider-neutral registry metadata for clients."""
        return {
            "id": self.id,
            "version": self.version,
            "title": self.title,
            "category": self.category,
            "inputs": [port.__dict__ for port in self.inputs],
            "outputs": [port.__dict__ for port in self.outputs],
            "modes": sorted(self.modes),
            "code_targets": sorted(self.code_targets),
            "required_capabilities": sorted(self.required_capabilities),
            "forbidden_capabilities": sorted(self.forbidden_capabilities),
            "config_schema": self.config_schema,
            "ui_schema": self.ui_schema,
            "hooks": {
                "validator": self.validator_hook,
                "compiler": self.compiler_hook,
                "schema_inference": self.schema_inference_hook,
                "preview": self.preview_hook,
            },
            "documentation_key": self.documentation_key,
        }

    def validate_config(self, config: dict[str, Any], node_id: str | None = None) -> list[Problem]:
        required = self.config_schema.get("required", [])
        return [
            Problem(
                code="SDPS-OPERATOR-001",
                severity="error",
                message=f"Missing required configuration: {name}",
                node_id=node_id,
                remediation=f"Set '{name}' in the operator inspector.",
            )
            for name in required
            if name not in config or config[name] in (None, "")
        ]


class OperatorRegistry:
    def __init__(self, definitions: list[OperatorDefinition] | None = None) -> None:
        self._definitions = {item.id: item for item in (definitions or [])}

    def register(self, definition: OperatorDefinition) -> None:
        if definition.id in self._definitions:
            raise ValueError(f"operator already registered: {definition.id}")
        self._definitions[definition.id] = definition

    def get(self, operator_id: str) -> OperatorDefinition:
        return self._definitions[operator_id]

    def all(self) -> tuple[OperatorDefinition, ...]:
        return tuple(self._definitions[key] for key in sorted(self._definitions))


def builtin_registry() -> OperatorRegistry:
    def ports(
        item: dict[str, Any], names_key: str, metadata_key: str
    ) -> tuple[PortDefinition, ...]:
        metadata = item.get(metadata_key, {})
        return tuple(
            PortDefinition(name, **(metadata.get(name, {}) if isinstance(metadata, dict) else {}))
            for name in item.get(names_key, [])
        )

    definitions = []
    for item in BUILTIN_OPERATORS:
        definitions.append(
            OperatorDefinition(
                id=item["id"],
                version=1,
                title=item["title"],
                category=item["category"],
                inputs=ports(item, "inputs", "inputPorts"),
                outputs=ports(item, "outputs", "outputPorts"),
                modes=frozenset(item.get("modes", ["batch", "streaming"])),
                code_targets=frozenset(item.get("codeTargets", ["python"])),
                required_capabilities=frozenset(item.get("required_capabilities", [])),
                forbidden_capabilities=frozenset(item.get("forbidden_capabilities", [])),
                config_schema={
                    "type": "object",
                    "required": [f["name"] for f in item.get("fields", []) if f.get("required")],
                },
                ui_schema={"fields": item.get("fields", [])},
                validator_hook=item.get(
                    "validator_hook", "sdpstudio_core.operators.validate_config"
                ),
                compiler_hook=item.get("compiler_hook"),
                schema_inference_hook=item.get("schema_inference_hook"),
                preview_hook=item.get("preview_hook"),
                documentation_key=item.get("documentation_key", f"operator.{item['id']}"),
            )
        )
    registry = OperatorRegistry(definitions)
    for item in discover_operator_plugins():
        try:
            registry.register(
                OperatorDefinition(
                    id=item["id"],
                    version=int(item.get("version", 1)),
                    title=item["title"],
                    category=str(item.get("category", "Extensions")),
                    inputs=tuple(PortDefinition(name) for name in item.get("inputs", [])),
                    outputs=tuple(PortDefinition(name) for name in item.get("outputs", [])),
                    modes=frozenset(item.get("modes", ["batch", "streaming"])),
                    code_targets=frozenset(item.get("code_targets", ["python"])),
                    required_capabilities=frozenset(item.get("required_capabilities", [])),
                    forbidden_capabilities=frozenset(item.get("forbidden_capabilities", [])),
                    config_schema=item.get("config_schema", {}),
                    ui_schema=item.get("ui_schema", {}),
                    validator_hook=item.get("validator_hook"),
                    compiler_hook=item.get("compiler_hook"),
                    schema_inference_hook=item.get("schema_inference_hook"),
                    preview_hook=item.get("preview_hook"),
                    documentation_key=item.get("documentation_key"),
                )
            )
        except (TypeError, ValueError):
            continue
    return registry
