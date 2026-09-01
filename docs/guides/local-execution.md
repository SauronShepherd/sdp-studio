# Local execution and preview

Preview is read-only and bounded. It returns rows, schema, profile information, and—when requested by the runtime—captured Spark plan artifacts. Preview and run artifacts are stored below `.sdpstudio/runtime` and are excluded from generated source.

Runs move through preparation, validation, submission, execution, artifact collection, and a terminal state. The durable worker claims queued runs with a lease, renews the heartbeat, and makes an expired claim eligible for recovery.
