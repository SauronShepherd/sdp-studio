# Concepts

## Pipeline document and IR

A pipeline document is the lossless visual representation. Code generation first validates and lowers it into immutable IR objects. The IR carries sources, transforms, sinks, expressions, execution mode, and secret/parameter references.

## Runs

Runs move through explicit preparation, validation, submission, execution, artifact collection, and terminal states. Non-terminal runs can be reconciled as `lost` after restart.

## Secrets

Secret references use `secret://name`. Values are encrypted at rest and resolved only at the execution boundary; snapshots, logs, and debug bundles redact them.

## Collaboration and history

Collaboration uses Yjs updates transported over a project WebSocket and durable optimistic revision checks. Local history is machine-local, ignored by Git, and supports retention plus named checkpoints.
