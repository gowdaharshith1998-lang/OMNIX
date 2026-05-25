package systems.axiomcontrol.omnix.scientist;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;

class ExperimentTest {

    @Test
    void agreementReturnsControlAndPublishesNothing() {
        List<Experiment.Mismatch> sink = new ArrayList<>();
        Experiment<Integer, Integer> exp = Experiment.<Integer, Integer>named("e")
            .use(x -> x + 1)
            .try_(x -> x + 1)
            .publisher(sink::add)
            .build();
        assertEquals(6, exp.run(5));
        assertTrue(sink.isEmpty());
    }

    @Test
    void mismatchIsPublished() {
        List<Experiment.Mismatch> sink = new ArrayList<>();
        Experiment<Integer, Integer> exp = Experiment.<Integer, Integer>named("e")
            .use(x -> x + 1)
            .try_(x -> x + 2)
            .publisher(sink::add)
            .build();
        assertEquals(6, exp.run(5));
        assertEquals(1, sink.size());
        assertEquals(7, sink.get(0).candidate().value());
    }

    @Test
    void candidateExceptionRecorded() {
        List<Experiment.Mismatch> sink = new ArrayList<>();
        Experiment<Integer, Integer> exp = Experiment.<Integer, Integer>named("e")
            .use(x -> x)
            .try_(x -> { throw new IllegalStateException("boom"); })
            .publisher(sink::add)
            .build();
        assertEquals(1, exp.run(1));
        assertEquals(1, sink.size());
        assertNotNull(sink.get(0).candidate().exception());
    }
}
