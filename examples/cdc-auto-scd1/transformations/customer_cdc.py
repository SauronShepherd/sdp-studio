from pyspark import pipelines as dp
from pyspark.sql import functions as F


@dp.table(name="customer_changes")
def customer_changes():
    return spark.readStream.table("bronze.customer_changes")


dp.create_auto_cdc_flow(
    target="silver_customers",
    source="customer_changes",
    keys=["id"],
    sequence_by=F.col("sequence"),
    stored_as_scd_type=1,
)
