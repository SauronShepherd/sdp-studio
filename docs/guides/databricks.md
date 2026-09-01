# Databricks integration

Databricks is optional. Install the adapter extra only when required and keep
the workspace URL explicit (`https://...`). Authentication is supplied through
the Studio secret/environment boundary and is never written to project files.

The managed adapter supports source upload, pipeline create/update, validate,
start, status, and cancel. The portable `databricks-connect` runtime profile is
available separately for Spark Connect execution. Provider identity and an
external run ID are returned in run details when available.

Contract tests are offline:

```bash
python -m pytest -q tests/test_databricks_adapter.py
```
