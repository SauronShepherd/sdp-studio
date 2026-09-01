# SDP Studio Apache Spark CDC example

This reference uses the Apache Spark 4.2 Auto CDC SCD Type 1 API. It is kept
separate from the portable batch example because it requires the Spark 4.2
runtime capability `auto_cdc_scd1` and a change feed containing `id`,
`sequence`, and `__START_AT`/`__END_AT` metadata as appropriate for the source.

Run the importer or use this file as a custom-code artifact when the selected
runtime does not advertise the capability; unsupported code is preserved rather
than rewritten.
