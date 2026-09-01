# Third-Party Notices

Runtime Python dependencies are declared in `pyproject.toml`. Optional Spark execution uses Apache Spark, licensed under Apache License 2.0.

Release builds generate a deterministic CycloneDX inventory with:

```text
make sbom
make license-check
```

The license gate fails for the denylisted GPL, AGPL, LGPL, SSPL, and Commons Clause families. `UNKNOWN` entries are retained in the SBOM and require maintainer review before release; they are not silently treated as approved.

## SQLGlot

SQLGlot is used to parse and validate generated Spark SQL before execution. SQLGlot is licensed
under the MIT License. See https://github.com/tobymao/sqlglot/blob/main/LICENSE for the complete
license text.

## Collaboration merge

`pycrdt` (MIT License) is installed by the default server distribution for
server-side Yrs/Yjs update merging. The `collaboration` extra remains as a
backward-compatible empty extra. See https://github.com/y-crdt/pycrdt for the
project and license.

## Frontend test tooling

The development-only React component test harness uses `@testing-library/react`,
`@testing-library/jest-dom`, and `jsdom`. These packages are distributed under
the MIT License and are not included in the production browser bundle.

## Development type checking

The development extra uses mypy (MIT License) and types-PyYAML (Apache License 2.0)
for static Python type checking; these packages are development-only dependencies.

## Accessibility E2E

The browser qualification suite uses `axe-core` through `@axe-core/playwright`
for automated accessibility checks. These packages are distributed under the
Mozilla Public License 2.0 and are development-only dependencies.
