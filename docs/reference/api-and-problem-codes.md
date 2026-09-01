# API and problem codes

The OpenAPI-described FastAPI surface is the compatibility boundary for projects, pipelines, runs, files, Git, runtime profiles, diagnostics, quality suites, and collaboration. User-visible failures use stable `SDPS-*` problem codes. The generated TypeScript contract is refreshed with `python scripts/openapi_client.py --from-app --check` and is a required CI gate.

Mutating browser requests require the authenticated role and CSRF protection. Provider tokens and project secrets are resolved through the encrypted Studio secret store and are never written to generated source or logs.
