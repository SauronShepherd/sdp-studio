# AGENTS.md

1. Read `docs/spec/SDP_STUDIO_SPEC.md` and relevant ADRs before architecture changes.
2. Work in focused tasks; preserve a runnable repository.
3. Do not add a dependency without documenting need and license.
4. Never add provider-specific behavior to `sdpstudio_core`.
5. Never use `shell=True`.
6. Never log or persist secret values in plaintext project files.
7. Every behavior change requires tests.
8. Every operator needs validation and code-generation coverage.
9. Runtime adapters must obey common run/probe contracts.
10. Generated source must be deterministic.
11. Never destructively rewrite unsupported user code.
12. Run formatting/lint/type/tests relevant to a change.
13. Keep patches focused.
14. API changes should remain OpenAPI-described.
15. Persisted schema changes require migration handling.
16. `.sdpstudio` schema changes require migration tests.
17. User-visible errors require stable problem codes.
18. Capabilities come from probes/config, not provider name assumptions.
19. Core code-generation tests make no network calls.
20. Default product works without Databricks credentials.
