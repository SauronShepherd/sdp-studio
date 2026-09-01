"""Run the real Spark-backed Row Trace acceptance test."""

from __future__ import annotations

import os
import subprocess
import sys


def main() -> int:
    env = os.environ.copy()
    spark_python = env.get("SDPSTUDIO_SPARK_PYTHON", sys.executable)
    env["SDPSTUDIO_RUN_SPARK_TRACE_TESTS"] = "1"
    env["PYSPARK_PYTHON"] = spark_python
    env["PYSPARK_DRIVER_PYTHON"] = spark_python
    result = subprocess.run(
        [spark_python, "-m", "pytest", "-q", "tests/test_debug.py", "-k", "spark_subgraph"],
        env=env,
        check=False,
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
