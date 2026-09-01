# ADR-005: React, XYFlow, and Monaco frontend

**Context:** SDP Studio needs a browser IDE with a graph canvas, typed ports, source editing,
keyboard accessibility, and a migration path from the legacy single-file SPA. The selected
libraries must remain compatible with the server's static asset deployment.

**Alternatives:** We considered retaining the legacy DOM canvas, adopting a canvas-only editor,
and using a different graph library. Those alternatives either lacked typed graph semantics,
source-editor capability, or an incremental migration path.

**Decision:** The long-term UI uses React with XYFlow for graph editing and Monaco for source editing.
Stateful server data remains in the API layer and lightweight local component state; additional
state/query/form libraries are introduced only when a concrete requirement justifies them.

**Consequences:** The legacy SPA remains only during the documented parity migration. The frontend
must keep generated OpenAPI types synchronized and preserve an accessible fallback for editor text.

**Migration/rollback:** New panels are added behind the React entrypoint while the legacy entrypoint
remains available until parity tests pass. If a dependency becomes unmaintained, its boundary is
kept behind feature components so the implementation can be replaced without changing API contracts.
