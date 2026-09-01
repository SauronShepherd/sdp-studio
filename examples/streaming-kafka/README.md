# SDP Studio streaming Kafka example

This example is an open-source local reference for a streaming table, a
streaming transform, and an external append sink. It expects Kafka at
`localhost:9092` with topic `orders`; Kafka is an example-only dependency and
is not required by SDP Studio itself.

Generate the project from the visual model or use the checked-in source:

```bash
sdpstudio import-python transformations/streaming_orders.py
```

The source is portable `pyspark.pipelines` code and can be reviewed or run
with the configured Spark runtime profile.
