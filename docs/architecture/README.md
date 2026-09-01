# Architecture

SDP Studio is divided into provider-neutral core semantics, deterministic code generation, a server/storage boundary, runtime adapters, and a web client.

## Boundaries

- `sdpstudio_core` owns the document model, graph validation, capabilities, diagnostics, operators, and canonical IR.
- `sdpstudio_codegen` lowers the IR to deterministic Python or SQL source. SQL syntax is validated with SQLGlot.
- `sdpstudio_server` owns persistence, authentication, REST/WebSocket APIs, Git, scheduling, and local-history policy.
- `sdpstudio_runners` owns runtime probing and execution contracts. Optional providers remain outside core.
- `sdpstudio_adapters_databricks` is optional and communicates through an injected client boundary.
- `web/` contains the Vite/React client; the legacy static client remains during feature-parity migration.

The default installation works without Databricks credentials and does not require a network call for core code generation.
