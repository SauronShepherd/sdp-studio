.PHONY: install dev serve test lint format doctor package release-manifest sbom license-check qualify verify python-format-check python-lint python-typecheck python-test web-lint web-test web-typecheck web-build web-e2e spark-smoke spark-smoke-wsl spark-connect-smoke
install:
	python3 -m pip install -e . --no-deps

dev:
	python3 -m pip install -e '.[dev]'

serve:
	PYTHONPATH=python python3 -m sdpstudio_cli.main serve --open

test:
	PYTHONPATH=python pytest

python-format-check:
	python -m ruff format --check python tests

python-lint:
	python -m ruff check python tests

python-typecheck:
	python -m mypy

python-test:
	PYTHONPATH=python python -m pytest

lint:
	ruff check python tests

web-lint:
	pnpm --filter @sdpstudio/web lint

web-test:
	pnpm --filter @sdpstudio/web test

web-typecheck:
	pnpm --filter @sdpstudio/web typecheck

web-build:
	pnpm --filter @sdpstudio/web build

web-e2e:
	pnpm --filter @sdpstudio/web exec playwright install chromium
	pnpm --filter @sdpstudio/web test:e2e

format:
	ruff format python tests

doctor:
	PYTHONPATH=python python3 -m sdpstudio_cli.main doctor

package:
	python3 -m build

release-manifest:
	python scripts/release_manifest.py --output dist/release-manifest.json pyproject.toml README.md LICENSE NOTICE

sbom:
	python scripts/sbom.py --output dist/sbom.cdx.json

license-check: sbom
	python scripts/license_gate.py dist/sbom.cdx.json

qualify:
	python scripts/qualify.py --browser --output dist/qualification.json

verify: python-format-check python-lint python-typecheck python-test web-lint web-test web-typecheck web-build license-check

spark-smoke:
	PYTHONPATH=python spark-submit --master local[2] tests/spark_preview_smoke.py

spark-smoke-wsl:
	wsl.exe -- bash -lc 'cd "$$(wslpath -a "$(CURDIR)")" && PYTHONPATH=python spark-submit --master local[2] tests/spark_preview_smoke.py'

spark-connect-smoke:
	PYTHONPATH=python python3 tests/spark_connect_smoke.py
