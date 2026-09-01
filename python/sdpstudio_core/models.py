from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .ids import new_ulid

Severity = Literal["info", "warning", "error"]

RUN_TRANSITIONS: dict[str, frozenset[str]] = {
    "created": frozenset({"queued", "failed", "cancelled", "lost"}),
    "queued": frozenset({"preparing", "failed", "cancelled", "lost"}),
    "preparing": frozenset({"validating", "failed", "cancelled", "lost"}),
    "validating": frozenset({"submitting", "validation_failed", "failed", "cancelled", "lost"}),
    "submitting": frozenset({"running", "failed", "cancelled", "lost"}),
    "running": frozenset({"collecting_artifacts", "failed", "cancelled", "lost"}),
    "collecting_artifacts": frozenset({"succeeded", "failed", "lost"}),
    "succeeded": frozenset(),
    "validation_failed": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
    "lost": frozenset(),
}


def is_valid_run_transition(current: str, target: str) -> bool:
    return current == target or target in RUN_TRANSITIONS.get(current, frozenset())


class Problem(BaseModel):
    code: str
    severity: Severity
    message: str
    node_id: str | None = None
    path: str | None = None
    line: int | None = Field(default=None, ge=1)
    doc_link: str | None = None
    probable_cause: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    remediation: str | None = None


class Position(BaseModel):
    x: float = 100
    y: float = 100


class PortRef(BaseModel):
    node: str
    port: str = "out"


class Node(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str = Field(default_factory=new_ulid)
    type: str
    operatorVersion: int = 1
    position: Position = Field(default_factory=Position)
    config: dict[str, Any] = Field(default_factory=dict)


class Edge(BaseModel):
    id: str = Field(default_factory=new_ulid)
    from_: PortRef = Field(alias="from")
    to: PortRef

    model_config = ConfigDict(populate_by_name=True)


class Port(BaseModel):
    """Persisted port declaration for typed graph contracts."""

    name: str
    direction: Literal["input", "output"]
    cardinality: Literal["one", "many"] = "one"
    modes: frozenset[Literal["batch", "streaming"]] = frozenset({"batch", "streaming"})


class Parameter(BaseModel):
    """Typed project parameter reference, never a secret value."""

    name: str
    data_type: Literal[
        "string",
        "integer",
        "float",
        "boolean",
        "date",
        "timestamp",
        "secret-ref",
        "enum",
        "json",
    ] = "string"
    required: bool = False
    default: Any | None = None
    choices: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_typed_value(self) -> Parameter:
        if self.data_type == "enum":
            if not self.choices or len(self.choices) != len(set(self.choices)):
                raise ValueError("enum parameters require unique choices")
            if self.default is not None and self.default not in self.choices:
                raise ValueError("enum parameter default must be one of choices")
        elif self.choices:
            raise ValueError("choices are only valid for enum parameters")
        if (
            self.data_type == "secret-ref"
            and self.default is not None
            and (not isinstance(self.default, str) or not self.default.startswith("secret://"))
        ):
            raise ValueError("secret-ref parameter defaults must use secret:// references")
        return self


class EnvironmentOverride(BaseModel):
    """Environment-specific settings without resolved secret material."""

    runtime_profile_id: str | None = None
    catalog: str | None = None
    schema_name: str | None = Field(default=None, alias="schema")
    spark_conf: dict[str, str] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)
    secret_references: dict[str, str] = Field(default_factory=dict)
    checkpoint_root: str | None = None
    deployment: dict[str, Any] = Field(default_factory=dict)


class EnvironmentReference(BaseModel):
    """Named environment binding persisted without its resolved value."""

    name: str
    variable: str
    required: bool = False
    overrides: EnvironmentOverride = Field(default_factory=EnvironmentOverride)


class PipelineDocument(BaseModel):
    schemaVersion: int = 1
    pipelineId: str = Field(default_factory=new_ulid)
    name: str = "main"
    revision: int = 0
    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)

    @model_validator(mode="after")
    def ensure_unique_ids(self) -> PipelineDocument:
        node_ids = [n.id for n in self.nodes]
        edge_ids = [e.id for e in self.edges]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("duplicate node ids")
        if len(edge_ids) != len(set(edge_ids)):
            raise ValueError("duplicate edge ids")
        return self


class ProjectMetadata(BaseModel):
    schemaVersion: int = 1
    projectId: str = Field(default_factory=new_ulid)
    name: str
    pipelines: list[dict[str, str]] = Field(default_factory=list)
    sparkSpec: str = "spark-pipeline.yaml"
    defaultLanguage: Literal["python", "sql"] = "python"
    compatibility: dict[str, str] = Field(
        default_factory=lambda: {"baseline": "spark-4.2", "mode": "portable-oss"}
    )
    parameters: list[Parameter] = Field(default_factory=list)
    environment_references: list[EnvironmentReference] = Field(default_factory=list)


class RuntimeExtension(BaseModel):
    """Typed metadata for an optional runtime capability extension."""

    model_config = ConfigDict(extra="allow")

    version: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class RuntimeCapabilities(BaseModel):
    adapter: str = "local"
    provider: str | None = None
    available: bool = False
    spark_version: str | None = None
    python: bool = True
    sql: bool = True
    sdp: bool = False
    dry_run: bool = False
    materialized_view: bool = True
    streaming_table: bool = True
    temporary_view: bool = True
    append_flow: bool = False
    sink: bool = False
    sinks: bool = False
    selective_refresh: bool = False
    full_refresh: bool = False
    spark_connect: bool = False
    auto_cdc_scd1: bool = False
    databricks: bool = False
    kubernetes: bool = False
    portability: Literal["portable", "provider", "unknown"] = "unknown"
    extensions: dict[str, RuntimeExtension] = Field(default_factory=dict)
    provider_extensions: dict[str, RuntimeExtension] = Field(default_factory=dict)
    downgrade_map: dict[str, str] = Field(default_factory=dict)
    details: dict[str, Any] = Field(default_factory=dict)


class GeneratedFile(BaseModel):
    path: str
    content: str
    sha256: str


class SourceRange(BaseModel):
    node_id: str
    file: str
    start_line: int
    end_line: int
    object_id: str | None = None
    start_column: int | None = None
    end_column: int | None = None
    content_hash: str | None = None


class GenerationResult(BaseModel):
    files: list[GeneratedFile]
    source_map: list[SourceRange]
    problems: list[Problem] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    diff_summary: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def populate_diff_summary(self) -> GenerationResult:
        if not self.changed_files:
            self.changed_files = [file.path for file in self.files]
        if not self.diff_summary:
            self.diff_summary = {"generated": len(self.files)}
        return self


class RunRecord(BaseModel):
    id: str = Field(default_factory=new_ulid)
    project_id: str
    status: Literal[
        "created",
        "queued",
        "preparing",
        "validating",
        "submitting",
        "running",
        "collecting_artifacts",
        "succeeded",
        "validation_failed",
        "failed",
        "cancelled",
        "lost",
    ] = "created"
    mode: str = "incremental"
    selected: list[str] = Field(default_factory=list)
    command: list[str] = Field(default_factory=list)
    code_hash: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    exit_code: int | None = None
    error: str | None = None
    pipeline_id: str | None = None
    runtime_profile_id: str | None = None
    run_type: str = "pipeline"
    graph_revision_hash: str | None = None
    git_commit: str | None = None
    git_dirty: bool = False
    dirty_patch_hash: str | None = None
    source_hash: str | None = None
    external_run_id: str | None = None


class RunEvent(BaseModel):
    seq: int
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    kind: str
    message: str
    data: dict[str, Any] = Field(default_factory=dict)


class RuntimeProfile(BaseModel):
    id: str = Field(default_factory=new_ulid)
    name: str
    # Built-ins are validated by the runtime registry; plugins may contribute
    # additional adapter identifiers without requiring a core release.
    adapter: str
    config: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
