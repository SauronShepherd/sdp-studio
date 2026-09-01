# Test organization

The current suite is intentionally runnable with a single `python -m pytest -q` command. Tests are grouped by concern in their module names while the repository migrates toward the specification's fixture/integration/adapter-contract/e2e directory layout.

- `test_core.py`, `test_ir.py`, and `test_architecture_contracts.py` cover core and code generation.
- `test_storage_api.py`, `test_run_state.py`, and `test_migrations.py` cover persistence and API behavior.
- `test_adapters.py`, `test_runtime_profiles.py`, and `test_databricks_adapter.py` cover runtime contracts.
- `tests/e2e/` is reserved for Playwright scenarios in `web/e2e/`.
