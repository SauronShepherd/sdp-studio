"""Run a bounded aggregation through an existing Spark Connect endpoint."""

from __future__ import annotations

import os

from pyspark.sql import SparkSession

remote = os.environ.get("SPARK_REMOTE", "sc://127.0.0.1:15002")
spark = SparkSession.builder.remote(remote).getOrCreate()
try:
    total = spark.range(1, 5).selectExpr("sum(id) AS total").collect()[0]["total"]
    print(f"SPARK_CONNECT_SUM {total} remote={remote}")
finally:
    spark.stop()
