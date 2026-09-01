# Quick start

Install the default product with Python 3.12 or newer:

```bash
python -m pip install -e '.[dev]'
sdpstudio doctor
sdpstudio serve
```

Open the printed local URL, create a project, select a runtime profile, validate
the graph, generate Python or SQL, and then submit a run. The default local
profile does not require Databricks credentials. Use `sdpstudio generate ID
--check` in CI to reject generated-source drift.

For local Spark execution install `.[pipelines]`; for Spark Connect install
`.[connect]`. Keep credentials in environment variables, an OS keyring, or a
registered Studio secret reference—never in pipeline YAML or generated source.
