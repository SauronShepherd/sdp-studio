from pyspark import pipelines as dp
from pyspark.sql import functions as F


@dp.table(name="raw_orders_stream")
def raw_orders_stream():
    return (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", "localhost:9092")
        .option("subscribe", "orders")
        .load()
        .select(F.col("timestamp"), F.col("value").cast("string").alias("payload"))
    )


@dp.table(name="orders_stream")
def orders_stream():
    return raw_orders_stream().where("payload IS NOT NULL")


@dp.create_sink(name="orders_audit", format="kafka", options={"topic": "orders-audit"})
def orders_audit():
    return orders_stream()
