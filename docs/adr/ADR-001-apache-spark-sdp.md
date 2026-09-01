# ADR-001: Apache Spark SDP as the execution contract

**Decision:** Generated pipelines target Apache Spark Declarative Pipelines and remain portable across runtime adapters.

**Consequences:** Provider integrations stay outside `sdpstudio_core`; capabilities are discovered at runtime.
