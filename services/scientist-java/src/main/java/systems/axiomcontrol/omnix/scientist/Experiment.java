package systems.axiomcontrol.omnix.scientist;

import java.util.Map;
import java.util.Objects;
import java.util.function.BiFunction;
import java.util.function.BooleanSupplier;
import java.util.function.Supplier;

/**
 * Drop-in OMNIX Scientist for Java services.
 *
 * <pre>{@code
 * Experiment<Order, Receipt> exp = Experiment.<Order, Receipt>named("checkout")
 *     .use(LegacyCheckout::process)
 *     .try_(NewCheckout::process)
 *     .publisher(JsonlPublisher.of("/var/log/omnix-mismatches.jsonl"))
 *     .build();
 * Receipt result = exp.run(order);
 * }</pre>
 */
public final class Experiment<I, O> {

    private final String name;
    private final java.util.function.Function<I, O> control;
    private final java.util.function.Function<I, O> candidate;
    private final ResultPublisher publisher;
    private final BiFunction<O, O, Boolean> comparator;
    private final BooleanSupplier enabled;

    private Experiment(Builder<I, O> b) {
        this.name = b.name;
        this.control = Objects.requireNonNull(b.control, "use(...) missing");
        this.candidate = b.candidate;
        this.publisher = b.publisher == null ? m -> {} : b.publisher;
        this.comparator = b.comparator == null ? Objects::equals : b.comparator;
        this.enabled = b.enabled == null ? () -> true : b.enabled;
    }

    public O run(I input) {
        long t0 = System.nanoTime();
        O controlValue;
        try {
            controlValue = control.apply(input);
        } catch (RuntimeException e) {
            throw e;
        }
        long controlMs = (System.nanoTime() - t0) / 1_000_000;
        if (candidate == null || !enabled.getAsBoolean()) return controlValue;
        long t1 = System.nanoTime();
        O candidateValue = null;
        String candidateException = null;
        try {
            candidateValue = candidate.apply(input);
        } catch (RuntimeException e) {
            candidateException = e.toString();
        }
        long candidateMs = (System.nanoTime() - t1) / 1_000_000;
        boolean agree = candidateException == null && comparator.apply(controlValue, candidateValue);
        if (!agree) {
            publisher.publish(new Mismatch(
                name,
                new Branch("control", controlValue, controlMs, null),
                new Branch("candidate", candidateValue, candidateMs, candidateException),
                Map.of("input", String.valueOf(input))
            ));
        }
        return controlValue;
    }

    public static <I, O> Builder<I, O> named(String name) {
        Builder<I, O> b = new Builder<>();
        b.name = name;
        return b;
    }

    public static final class Builder<I, O> {
        private String name;
        private java.util.function.Function<I, O> control;
        private java.util.function.Function<I, O> candidate;
        private ResultPublisher publisher;
        private BiFunction<O, O, Boolean> comparator;
        private BooleanSupplier enabled;

        public Builder<I, O> use(java.util.function.Function<I, O> fn) { this.control = fn; return this; }
        public Builder<I, O> try_(java.util.function.Function<I, O> fn) { this.candidate = fn; return this; }
        public Builder<I, O> publisher(ResultPublisher p) { this.publisher = p; return this; }
        public Builder<I, O> comparator(BiFunction<O, O, Boolean> c) { this.comparator = c; return this; }
        public Builder<I, O> enabled(BooleanSupplier e) { this.enabled = e; return this; }
        public Experiment<I, O> build() { return new Experiment<>(this); }
    }

    public record Branch(String name, Object value, long durationMs, String exception) {}
    public record Mismatch(String experiment, Branch control, Branch candidate, Map<String, String> context) {}

    public interface ResultPublisher {
        void publish(Mismatch mismatch);
    }
}
