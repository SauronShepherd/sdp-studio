# Governance

SDP Studio uses an open contribution model under Apache-2.0. Contributors may
propose issues, documentation, code, and architecture decisions. Maintainers
are responsible for release quality, security response, and stewardship of the
project's compatibility and naming commitments.

## Decision process

Routine fixes may be merged by one maintainer after review. Changes affecting
public APIs, persistence, execution semantics, security boundaries, provider
isolation, or collaboration require an ADR and approval from two maintainers
when available. ADRs record the context, alternatives, decision, and migration
or rollback plan.

Consensus is preferred. If consensus cannot be reached, the maintainers make a
documented decision based on user impact, security, portability, operability,
and the governing specification. A decision may be revisited when new evidence
or a material requirement appears.

## Releases and maintainership

Release candidates must pass the repository qualification gates and include
release notes for user-visible or migration-impacting changes. Security issues
follow `SECURITY.md` and may be handled privately until a fix is available.
Maintainers can add or retire maintainers by documented consensus; inactive
maintainers may step down or be rotated out after notice.
