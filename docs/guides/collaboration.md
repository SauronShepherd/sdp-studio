# Collaboration

The browser collaboration channel is `/ws/collab/{project_id}` (the legacy
`/ws/projects/{project_id}` alias remains supported). Yjs updates are persisted,
replayed after reconnect, and compare-and-swap protects pipeline revisions.
Viewers can receive updates but cannot publish edits.

Generated Python and SQL use ownership markers. Supported edits reconcile into
the graph; unsupported edits remain custom-owned and return stable
`SDPS-RECON-*` problems instead of being overwritten. Flush collaborative edits
before Git checkout, pull, or conflict resolution.
