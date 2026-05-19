# COBOL Demo

The demo is a pure batch COBOL rebuild pipeline:

1. Ingest the repository graph.
2. Capture behavior per fixture.
3. Generate Hypothesis specs from captures.
4. Rebuild COBOL programs to Python replicas through real fabric LLM dispatch.
5. Verify signed rebuild receipts with Gates 1-6.

Programs:

1. `TC011A`, `TC012A`, `TC101M`: baseline NIST behavioral replication.
2. `TC201C`: copybook resolution through `COPY CUSTREC`.
3. `TC301E`: EBCDIC source normalization, with a UTF-8 reference for grading.
4. `TC401P`: COMP-3 packed decimal arithmetic and edited-picture formatting.
