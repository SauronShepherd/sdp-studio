# Runtime profiles

Runtime profiles describe an adapter and its configuration without storing credentials in the project document. Local profiles use the installed Spark command when available. Databricks profiles use workspace/catalog/schema settings and a secret reference; Kubernetes profiles use an image, namespace, service account, and executor settings.

Use **Probe** before running. Capabilities come from the probe and configured runtime version, not from the provider name alone. A run is submitted through the durable queue and can be inspected, cancelled, or reconciled after a server restart.
