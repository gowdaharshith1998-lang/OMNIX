# OMNIX Mainframe Observation Subchart

In-cluster bridge containers that consume vendor-emitted Kafka messages from
mainframe-side observation agents and forward normalized `Observation`
envelopes to the OMNIX collector.

## Status

This is an optional enterprise chart surface. The mainframe-side capture agents
remain customer-licensed and operated outside this chart; OMNIX deploys only
the in-cluster bridge workers.

## Vendor matrix

| Vendor | Source | Delivery | License |
|---|---|---|---|
| **tcVISION** | VSAM / Db2 z/OS | Confluent Kafka, EBCDIC-converted | Customer-licensed |
| **Ironstream** | SMF / SYSLOG | Confluent Kafka, SMF binary records | Customer-licensed |
| **C\Prof** | CICS internal trace | Confluent Kafka, JSON | Customer-licensed |

The mainframe-side product (the agent that captures and ships) is
**customer-licensed**. This subchart deploys the in-cluster consumer only.

## Enabling

In the parent chart's values, set `mainframe.enabled=true` and turn on each
vendor you need:

```yaml
mainframe:
  enabled: true
  tcvision:
    enabled: true
    topic: "tcvision.records"
    bootstrapServers: "kafka.platform:9092"
```

Each bridge currently accepts topic, bootstrap servers, and consumer group
through chart values (`OMNIX_MAINFRAME_TOPIC`, `OMNIX_MAINFRAME_BOOTSTRAP`,
`OMNIX_MAINFRAME_GROUP`). If the Kafka cluster requires SASL/TLS, add the
required Secret mounts or env wiring before enabling the bridge in production.

## Bridge behavior

- Bridges are plain Python worker processes that consume the configured
  topic and POST each batch to the collector at `OMNIX_COLLECTOR_URL`.
- Vendor-specific wire-format handling lives in
  `src/omnix/cloud/observe/mainframe_bridge.py`:
  - tcVISION: EBCDIC-converted UTF-8 with a 24-byte VSAM record header (skipped)
  - Ironstream: SMF records with an 8-byte header (`struct.unpack` to extract
    type/subtype before routing through `collect_smf`)
  - C\Prof: JSON-line CICS trace, no preprocessing
- Bridges declare both `aiokafka` and `confluent-kafka-python` as optional
  imports. If neither is installed the bridge logs a fatal error and exits 0
  so the pod's `CrashLoopBackOff` is visible without burning restart budget.

## Audit notes

Mainframe observation can contribute to a regulator-facing audit trail and shares
the OMNIX `Observation` envelope (`src/omnix/cloud/observe/envelope.py`),
which carries `redacted_fields` per record. PII redaction patterns are
inherited from the parent — emails, SSNs, PANs, IPv4.
