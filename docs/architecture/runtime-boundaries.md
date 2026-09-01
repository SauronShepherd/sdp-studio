# Runtime boundaries

SDP Studio keeps the portable graph, validation, IR, and deterministic code generation in `sdpstudio_core` and `sdpstudio_codegen`. Server adapters implement the asynchronous probe, validation, preview, submission, status, event, and artifact contracts. Provider-specific settings stay in runtime profiles and adapters; they are not imported into core graph semantics.

Runs are persisted before execution. The worker claims queued runs, records leases and events, and recovers stale claims. Local execution is the default and requires no Databricks credentials.
