# Guides

## Local quickstart

From the repository root:

```text
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
sdpstudio doctor
sdpstudio serve
```

The doctor command reports whether local Spark/Pipelines tooling is available. Core validation and generation remain usable when Spark is absent. Databricks and Kubernetes are optional runtime profiles.

More focused guides:

- [Quick start](quickstart.md)
- [Kubernetes runtime](kubernetes.md)
- [Databricks integration](databricks.md)
- [Collaboration](collaboration.md)
- [Security administration](security-admin.md)
- [Plugin development](plugin-development.md)

## Safe team deployment

Use a non-loopback bind only with authentication configured. Set `SDPSTUDIO_DATABASE_URL` for team persistence, configure the authentication signing key, and use the protected runtime-profile flag for production execution targets.
