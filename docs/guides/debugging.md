# Debugging

The Debug panel exposes captured plans, row trace, recent-run comparison, schema/profile changes, and Kubernetes run details where supported by the runtime. Plan artifacts and event-log summaries are collected under the run artifact directory.

Row trace reports provenance and bounded input/output counts. It marks operators whose exact attribution is unavailable instead of presenting an estimate as exact. Debug bundles redact registered secrets and include a manifest with artifact hashes.
