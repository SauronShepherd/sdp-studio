# Security and administration

Do not place token, password, private-key, or other secret values in pipeline configuration. Store a `secret://` reference and resolve the value only at the runtime boundary. Debug bundles and structured logs redact secret-shaped fields and registered secret values.

The server uses authenticated sessions, CSRF protection for browser mutations, role checks, request IDs, readiness checks, secure response headers, and Kubernetes administrator allowlists. Keep the application secret key and database credentials outside the repository and rotate them through the deployment secret manager.
