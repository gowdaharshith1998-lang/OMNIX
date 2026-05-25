# omnix-scientist (Java)

Drop-in GitHub-Scientist port for Java services migrating to OMNIX-replicated targets.

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

The experiment always returns the **control** result — your users never see
candidate-side drift. Mismatches are published asynchronously to your sink of
choice.
