# omnix-scientist for Java

Java adapter for dual-running a legacy implementation and a candidate
implementation while OMNIX collects mismatch evidence.

## Status

This package is an adapter surface for private pilots and service-side
experiments. The experiment always returns the control result; candidate drift
is published asynchronously to the configured sink.

## Requirements

- JDK 17+
- Maven 3.9+

## Maven

```xml
<dependency>
    <groupId>systems.axiomcontrol.omnix</groupId>
    <artifactId>omnix-scientist</artifactId>
    <version>0.1.0</version>
</dependency>
```

## Usage

```java
Experiment<Order, Receipt> exp = Experiment.<Order, Receipt>named("checkout")
    .use(LegacyCheckout::process)
    .try_(NewCheckout::process)
    .publisher(JsonlPublisher.of(Path.of("/var/log/omnix-mismatches.jsonl")))
    .build();

Receipt result = exp.run(order);
```

## Verification

Run package-specific checks from this directory when Maven is available:

```bash
mvn test
```

## Operational Notes

- The control result is always returned to the caller.
- Mismatches are review evidence; they do not automatically approve a cutover.
- Customer services should decide where mismatch logs are retained and who can
  access them.
