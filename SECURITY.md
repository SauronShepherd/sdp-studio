# Security Policy

Please report suspected vulnerabilities privately to the project maintainers rather than opening a public issue. Do not include credentials, tokens, customer data, or production debug bundles in a report.

## Deployment defaults

SDP Studio defaults to `127.0.0.1`. A non-loopback CLI bind is refused unless `SDPSTUDIO_AUTH_TOKEN` is configured or the operator explicitly supplies `--insecure-allow-remote`.

For a shared deployment:

```bash
export SDPSTUDIO_AUTH_TOKEN='use-a-long-random-secret'
sdpstudio serve --host 0.0.0.0 --port 8787
```

Use TLS at a trusted reverse proxy for any network that is not fully trusted. Restrict inbound traffic with firewall/network policy. The MVP uses one shared bearer token; it does **not** yet provide per-user OIDC/SAML identities or granular RBAC.

Browser HTTP requests send the token in the `Authorization: Bearer` header. Collaboration WebSockets carry an encoded token in the negotiated WebSocket subprotocol header rather than the URL/query string, reducing accidental credential exposure in access logs. The application stores the browser token in local storage, so use a dedicated SDP Studio token and protect the browser/device accordingly.

## Secret handling

- Do not put credentials directly in visual operator/runtime configuration.
- Runtime profiles support environment-variable references such as `remote_env`.
- GitHub/GitLab provider tokens are read from environment variables and are not written into SDP Studio projects.
- HTTP Git URLs with embedded credentials are rejected.
- Git local/file/ext helper transports are rejected by server-managed clone/remote operations.
- Spark/Git subprocesses use argument arrays and `shell=False`.
- Persisted run output is redacted for common secret/token/password patterns, but debug bundles may still contain business data. Review them before sharing.

## Production boundary

SDP Studio 0.1.0 is intended for trusted engineering teams and controlled infrastructure. Before exposing it as a multi-tenant internet service, add external identity, granular authorization, centralized audit logging, secret-manager integration, distributed collaboration/session storage, rate limiting, and deployment-specific sandboxing for execution workers.
