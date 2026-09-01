from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from sqlglot import exp, parse


@dataclass(frozen=True)
class SqlDeclaration:
    name: str
    kind: str
    file: str
    start_line: int
    end_line: int
    dependencies: tuple[str, ...] = ()


@dataclass(frozen=True)
class SqlCustomCodeArtifact:
    file: str
    start_line: int
    end_line: int
    source: str
    reason: str
    source_sha256: str


@dataclass(frozen=True)
class SqlImportReport:
    declarations: tuple[SqlDeclaration, ...]
    source_sha256: str
    custom_code: tuple[SqlCustomCodeArtifact, ...] = ()


_DECLARATION = re.compile(
    r"(?im)^\s*CREATE\s+(?:OR\s+REPLACE\s+)?(?:(MATERIALIZED\s+VIEW)|(STREAMING\s+TABLE)|(TEMPORARY\s+VIEW|TEMP\s+VIEW))\s+([\w.`-]+)"
)


def discover_sql(path: Path, source: str | None = None) -> SqlImportReport:
    text = source if source is not None else path.read_text(encoding="utf-8")
    declarations = []
    kind_map = {
        1: "dataset.materialized_view",
        2: "dataset.streaming_table",
        3: "dataset.temporary_view",
    }
    matches = list(_DECLARATION.finditer(text))
    try:
        parsed = [
            statement
            for statement in parse(text, read="spark")
            if isinstance(statement, exp.Create)
        ]
    except Exception:
        parsed = []
    for declaration_index, match in enumerate(matches):
        kind = next(kind_map[index] for index in range(1, 4) if match.group(index))
        start_line = text.count("\n", 0, match.start()) + 1
        end_line = text.count("\n", 0, match.end()) + 1
        dependencies: tuple[str, ...] = ()
        statement = parsed[declaration_index] if declaration_index < len(parsed) else None
        if statement is not None:
            target = match.group(4).strip("`")
            cte_names = {cte.alias_or_name for cte in statement.find_all(exp.CTE)}
            dependencies = tuple(
                sorted(
                    {
                        ".".join(
                            part for part in (table.catalog, table.db, table.name) if part
                        ).strip("`")
                        for table in statement.find_all(exp.Table)
                        if ".".join(
                            part for part in (table.catalog, table.db, table.name) if part
                        ).strip("`")
                        != target
                        and table.name not in cte_names
                    }
                )
            )
        declarations.append(
            SqlDeclaration(
                match.group(4).strip("`"), kind, str(path), start_line, end_line, dependencies
            )
        )
    if not matches and parsed:
        # SQLGlot is the authoritative fallback for standard CREATE VIEW/TABLE
        # forms that are not SDP-specific syntax. They are imported as batch
        # materialized views and retain their relational dependencies.
        for statement in parsed:
            if (statement.kind or "").upper() not in {"VIEW", "TABLE"} or not isinstance(
                statement.this, exp.Table
            ):
                continue
            name = statement.this.name
            serialized = statement.sql(dialect="spark")
            offset = text.upper().find("CREATE")
            start_line = text.count("\n", 0, max(0, offset)) + 1
            end_line = start_line + serialized.count("\n")
            cte_names = {cte.alias_or_name for cte in statement.find_all(exp.CTE)}
            dependencies = tuple(
                sorted(
                    {
                        ".".join(
                            part for part in (table.catalog, table.db, table.name) if part
                        ).strip("`")
                        for table in statement.find_all(exp.Table)
                        if table is not statement.this and table.name not in cte_names
                    }
                )
            )
            declarations.append(
                SqlDeclaration(
                    name, "dataset.materialized_view", str(path), start_line, end_line, dependencies
                )
            )
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    custom_code: tuple[SqlCustomCodeArtifact, ...] = ()
    if not declarations or re.search(
        r"(?im)^\s*(INSERT|UPDATE|DELETE|MERGE|GRANT|ALTER|DROP)\b", text
    ):
        custom_code = (
            SqlCustomCodeArtifact(
                str(path),
                1,
                max(1, text.count("\n") + 1),
                text,
                "Unsupported or code-owned SQL was preserved verbatim",
                digest,
            ),
        )
    return SqlImportReport(tuple(declarations), digest, custom_code)
