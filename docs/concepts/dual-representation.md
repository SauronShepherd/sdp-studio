# Dual representation

The persisted pipeline document is the semantic source of truth. React Flow contributes layout and interaction state, while generated Python or SQL carries source maps and ownership metadata. Supported edits can be reconciled through the Level-B reconciliation service; unsupported or ambiguous edits produce a structured report and are preserved rather than destructively rewritten.

Secrets are represented only by references such as `secret://name`; resolved values remain in memory at the runtime boundary.
