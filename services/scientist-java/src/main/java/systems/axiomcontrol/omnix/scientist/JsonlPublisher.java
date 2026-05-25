package systems.axiomcontrol.omnix.scientist;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public final class JsonlPublisher {
    private JsonlPublisher() {}

    public static Experiment.ResultPublisher of(Path path) {
        ObjectMapper mapper = new ObjectMapper();
        return (m) -> {
            try {
                Files.createDirectories(path.getParent());
                String line = mapper.writeValueAsString(m) + "\n";
                Files.writeString(path, line, StandardOpenOption.CREATE, StandardOpenOption.APPEND);
            } catch (IOException e) {
                // swallow — never break the request path on publish failure
            }
        };
    }
}
