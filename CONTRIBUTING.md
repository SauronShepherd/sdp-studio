# Contributing

## Before opening a change

Read `AGENTS.md`, `docs/spec/SDP_STUDIO_SPEC.md`, the relevant ADRs, and the
affected package documentation. Keep a change focused and describe the user
visible behavior, compatibility impact, and verification performed.

## Engineering rules

- Keep provider-specific behavior outside `sdpstudio_core`.
- Add or update tests for every behavior change. Code-generation changes require
  deterministic output coverage and an explicit no-data-loss test.
- API changes require OpenAPI regeneration and migration changes require an
  Alembic revision plus upgrade coverage.
- Never persist or log secrets, use `shell=True`, or destructively rewrite
  unsupported user code.
- New dependencies require a documented purpose, license, and notice update.

## Review and validation

Run `make test` (or the equivalent Python and web gates) before submitting.
Changes are reviewed for correctness, security, portability, accessibility,
documentation, and test evidence. A maintainer may request a focused design
review or ADR before merging architectural changes.

Pull requests should include:

1. A concise problem statement and implementation summary.
2. Tests and commands run, including any environment-dependent omissions.
3. Migration, API, generated-file, or documentation notes when applicable.
4. Confirmation that no credentials or customer data are included.
