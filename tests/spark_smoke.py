from pyspark.sql import SparkSession

spark = SparkSession.builder.master("local[2]").appName("sdpstudio-smoke").getOrCreate()
try:
    rows = [(1, "COMPLETE", 10.5), (2, "CANCELLED", 4.0), (3, "COMPLETE", 2.5)]
    frame = spark.createDataFrame(rows, ["id", "status", "amount"])
    result = frame.filter("status = 'COMPLETE'").groupBy().sum("amount").collect()[0][0]
    print(f"SDP_SPARK_SMOKE sum={result} version={spark.version}")
finally:
    spark.stop()
