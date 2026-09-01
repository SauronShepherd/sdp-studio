# Code synchronization

Generated Python and SQL contain `sdpstudio:region` ownership markers and source-map metadata. The visual document is the semantic input for generation. When source is edited, use **Reconcile into graph** to parse supported changes.

Supported changes update the visual configuration and can be regenerated deterministically. If a change is not representable, reconciliation returns a stable problem and preserves the source as custom-owned. Generation refuses to overwrite a changed owned region unless ownership can be proven, preventing accidental loss of user code.
