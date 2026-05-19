/*
 * EquivalenceProbeRunner - single-source, single-probe runner for OMNIX gate 6.
 *
 * It intentionally handles one side of one probe. The Python orchestrator forks
 * this runner once for legacy and once for rebuilt source, so System.exit(),
 * timeout, or VM death affects only that side of that probe.
 */

import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.FileObject;
import javax.tools.ForwardingJavaFileManager;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileManager;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.PrintStream;
import java.io.Reader;
import java.lang.reflect.Array;
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class EquivalenceProbeRunner {
    private EquivalenceProbeRunner() {}

    public static void main(String[] args) {
        try {
            @SuppressWarnings("unchecked")
            Map<String, Object> payload = (Map<String, Object>) new JsonParser(readAll()).parse();
            run(payload);
        } catch (Throwable ex) {
            ex.printStackTrace(System.err);
            System.exit(1);
        }
    }

    private static void run(Map<String, Object> payload) throws Exception {
        String source = requireString(payload, "source");
        String className = requireString(payload, "class_name");
        String methodName = requireString(payload, "method_name");
        List<String> parameterTypes = requireStringList(payload, "parameter_types");
        List<Object> probe = requireList(payload, "probe");

        ClassLoader loader = compile(className, source);
        Class<?> clazz = loader.loadClass(className);
        Method method = findMethod(clazz, methodName, parameterTypes);
        Object[] args = convertArgs(probe, method.getParameterTypes());

        PrintStream oldOut = System.out;
        PrintStream oldErr = System.err;
        ByteArrayOutputStream stdout = new ByteArrayOutputStream();
        ByteArrayOutputStream stderr = new ByteArrayOutputStream();
        long start = System.nanoTime();
        Map<String, Object> out = new LinkedHashMap<>();
        try {
            System.setOut(new PrintStream(stdout, true, StandardCharsets.UTF_8));
            System.setErr(new PrintStream(stderr, true, StandardCharsets.UTF_8));
            Object receiver = null;
            if (!Modifier.isStatic(method.getModifiers())) {
                Constructor<?> ctor = clazz.getDeclaredConstructor();
                ctor.setAccessible(true);
                receiver = ctor.newInstance();
            }
            Object value = method.invoke(receiver, args);
            out.put("outcome", "returned");
            out.put("return_value", jsonValue(value));
            out.put("exception", null);
        } catch (InvocationTargetException ex) {
            out.put("outcome", "threw");
            out.put("return_value", null);
            out.put("exception", ex.getTargetException().getClass().getName());
        } catch (Throwable ex) {
            out.put("outcome", "threw");
            out.put("return_value", null);
            out.put("exception", ex.getClass().getName());
        } finally {
            System.setOut(oldOut);
            System.setErr(oldErr);
        }
        long elapsedMs = Math.max(0L, (System.nanoTime() - start) / 1_000_000L);
        out.put("wall_clock_ms", elapsedMs);
        out.put("wall_clock_bucket", wallClockBucket(elapsedMs));
        out.put("stdout_sha256", sha256Hex(stdout.toByteArray()));
        out.put("stderr_sha256", sha256Hex(stderr.toByteArray()));
        System.out.println(toJson(out));
    }

    private static ClassLoader compile(String className, String source) {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("no system JavaCompiler available; run under a JDK");
        }
        DiagnosticCollector<JavaFileObject> diagnostics = new DiagnosticCollector<>();
        StandardJavaFileManager standard = compiler.getStandardFileManager(
            diagnostics,
            null,
            StandardCharsets.UTF_8
        );
        MemoryFileManager manager = new MemoryFileManager(standard);
        JavaFileObject sourceObject = new SourceFileObject(className, source);
        Boolean ok = compiler.getTask(null, manager, diagnostics, null, null, Arrays.asList(sourceObject)).call();
        if (!Boolean.TRUE.equals(ok)) {
            StringBuilder sb = new StringBuilder("compile failed");
            for (Diagnostic<? extends JavaFileObject> d : diagnostics.getDiagnostics()) {
                sb.append("\n").append(d.getKind()).append(" line ")
                    .append(d.getLineNumber()).append(": ").append(d.getMessage(null));
            }
            throw new IllegalArgumentException(sb.toString());
        }
        return new MemoryClassLoader(manager.classBytes());
    }

    private static Method findMethod(Class<?> clazz, String methodName, List<String> parameterTypes)
        throws NoSuchMethodException {
        for (Method method : clazz.getDeclaredMethods()) {
            if (!method.getName().equals(methodName) || method.getParameterCount() != parameterTypes.size()) {
                continue;
            }
            Class<?>[] actualTypes = method.getParameterTypes();
            boolean match = true;
            for (int i = 0; i < actualTypes.length; i++) {
                if (!typeMatches(actualTypes[i], parameterTypes.get(i))) {
                    match = false;
                    break;
                }
            }
            if (match) {
                method.setAccessible(true);
                return method;
            }
        }
        throw new NoSuchMethodException(clazz.getName() + "." + methodName);
    }

    private static boolean typeMatches(Class<?> actual, String expected) {
        if (actual.isArray()) {
            return (actual.getComponentType().getName() + "[]").equals(expected)
                || actual.getName().equals(expected);
        }
        return actual.getName().equals(expected);
    }

    private static Object[] convertArgs(List<Object> values, Class<?>[] parameterTypes) {
        Object[] out = new Object[values.size()];
        for (int i = 0; i < values.size(); i++) {
            out[i] = convertValue(values.get(i), parameterTypes[i]);
        }
        return out;
    }

    private static Object convertValue(Object value, Class<?> targetType) {
        if (value == null) return null;
        if (targetType == String.class) return String.valueOf(value);
        if (targetType == boolean.class || targetType == Boolean.class) return (Boolean) value;
        if (targetType == int.class || targetType == Integer.class) return Integer.valueOf(((Number) value).intValue());
        if (targetType == long.class || targetType == Long.class) return Long.valueOf(((Number) value).longValue());
        if (targetType == double.class || targetType == Double.class) return Double.valueOf(((Number) value).doubleValue());
        if (targetType == float.class || targetType == Float.class) return Float.valueOf(((Number) value).floatValue());
        if (targetType.isArray()) {
            @SuppressWarnings("unchecked")
            List<Object> raw = (List<Object>) value;
            Class<?> component = targetType.getComponentType();
            Object arr = Array.newInstance(component, raw.size());
            for (int i = 0; i < raw.size(); i++) Array.set(arr, i, convertValue(raw.get(i), component));
            return arr;
        }
        if (List.class.isAssignableFrom(targetType)) return new ArrayList<>((List<?>) value);
        if (Set.class.isAssignableFrom(targetType)) return new LinkedHashSet<>((List<?>) value);
        return value;
    }

    private static String wallClockBucket(long ms) {
        if (ms < 1) return "<1ms";
        if (ms < 10) return "<10ms";
        if (ms < 100) return "<100ms";
        if (ms < 1000) return "<1s";
        if (ms < 10000) return "<10s";
        return ">10s";
    }

    private static Object jsonValue(Object value) {
        if (value == null || value instanceof String || value instanceof Number || value instanceof Boolean) return value;
        Class<?> c = value.getClass();
        if (c.isArray()) {
            int n = Array.getLength(value);
            List<Object> out = new ArrayList<>(n);
            for (int i = 0; i < n; i++) out.add(jsonValue(Array.get(value, i)));
            return out;
        }
        return String.valueOf(value);
    }

    private static String sha256Hex(byte[] bytes) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(bytes);
            StringBuilder sb = new StringBuilder();
            for (byte b : digest) sb.append(String.format("%02x", b & 0xff));
            return sb.toString();
        } catch (Exception ex) {
            throw new IllegalStateException(ex);
        }
    }

    private static String readAll() throws IOException {
        StringBuilder sb = new StringBuilder();
        char[] buf = new char[8192];
        try (Reader reader = new InputStreamReader(System.in, StandardCharsets.UTF_8)) {
            int n;
            while ((n = reader.read(buf)) != -1) sb.append(buf, 0, n);
        }
        return sb.toString();
    }

    private static String requireString(Map<String, Object> payload, String key) {
        Object value = payload.get(key);
        if (!(value instanceof String)) throw new IllegalArgumentException("missing string key: " + key);
        return (String) value;
    }

    private static List<String> requireStringList(Map<String, Object> payload, String key) {
        List<Object> raw = requireList(payload, key);
        List<String> out = new ArrayList<>();
        for (Object value : raw) out.add((String) value);
        return out;
    }

    private static List<Object> requireList(Map<String, Object> payload, String key) {
        Object value = payload.get(key);
        if (!(value instanceof List)) throw new IllegalArgumentException("missing array key: " + key);
        @SuppressWarnings("unchecked")
        List<Object> out = (List<Object>) value;
        return out;
    }

    private static String toJson(Object value) {
        if (value == null) return "null";
        if (value instanceof String) return jsonString((String) value);
        if (value instanceof Number || value instanceof Boolean) return String.valueOf(value);
        if (value instanceof Map) {
            StringBuilder sb = new StringBuilder("{");
            boolean first = true;
            for (Map.Entry<?, ?> entry : ((Map<?, ?>) value).entrySet()) {
                if (!first) sb.append(',');
                first = false;
                sb.append(jsonString(String.valueOf(entry.getKey()))).append(':').append(toJson(entry.getValue()));
            }
            return sb.append('}').toString();
        }
        if (value instanceof Iterable) {
            StringBuilder sb = new StringBuilder("[");
            boolean first = true;
            for (Object item : (Iterable<?>) value) {
                if (!first) sb.append(',');
                first = false;
                sb.append(toJson(item));
            }
            return sb.append(']').toString();
        }
        return jsonString(String.valueOf(value));
    }

    private static String jsonString(String s) {
        StringBuilder sb = new StringBuilder("\"");
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '"': sb.append("\\\""); break;
                case '\\': sb.append("\\\\"); break;
                case '\b': sb.append("\\b"); break;
                case '\f': sb.append("\\f"); break;
                case '\n': sb.append("\\n"); break;
                case '\r': sb.append("\\r"); break;
                case '\t': sb.append("\\t"); break;
                default:
                    if (c < 0x20) sb.append(String.format("\\u%04x", (int) c));
                    else sb.append(c);
            }
        }
        return sb.append('"').toString();
    }

    private static final class SourceFileObject extends SimpleJavaFileObject {
        private final String source;
        SourceFileObject(String className, String source) {
            super(URI.create("string:///" + className.replace('.', '/') + Kind.SOURCE.extension), Kind.SOURCE);
            this.source = source;
        }
        @Override public CharSequence getCharContent(boolean ignoreEncodingErrors) { return source; }
    }

    private static final class ByteCodeFileObject extends SimpleJavaFileObject {
        private final ByteArrayOutputStream out = new ByteArrayOutputStream();
        ByteCodeFileObject(String className, Kind kind) {
            super(URI.create("bytes:///" + className.replace('.', '/') + kind.extension), kind);
        }
        @Override public ByteArrayOutputStream openOutputStream() { return out; }
        byte[] bytes() { return out.toByteArray(); }
    }

    private static final class MemoryFileManager extends ForwardingJavaFileManager<JavaFileManager> {
        private final Map<String, ByteCodeFileObject> compiled = new LinkedHashMap<>();
        MemoryFileManager(JavaFileManager fileManager) { super(fileManager); }
        @Override
        public JavaFileObject getJavaFileForOutput(Location location, String className, JavaFileObject.Kind kind, FileObject sibling) {
            ByteCodeFileObject file = new ByteCodeFileObject(className, kind);
            compiled.put(className, file);
            return file;
        }
        Map<String, byte[]> classBytes() {
            Map<String, byte[]> out = new LinkedHashMap<>();
            for (Map.Entry<String, ByteCodeFileObject> entry : compiled.entrySet()) out.put(entry.getKey(), entry.getValue().bytes());
            return out;
        }
    }

    private static final class MemoryClassLoader extends ClassLoader {
        private final Map<String, byte[]> classes;
        MemoryClassLoader(Map<String, byte[]> classes) {
            super(EquivalenceProbeRunner.class.getClassLoader());
            this.classes = classes;
        }
        @Override protected Class<?> findClass(String name) throws ClassNotFoundException {
            byte[] bytes = classes.get(name);
            if (bytes == null) throw new ClassNotFoundException(name);
            return defineClass(name, bytes, 0, bytes.length);
        }
    }

    private static final class JsonParser {
        private final String input;
        private int pos = 0;
        JsonParser(String input) { this.input = input; }
        Object parse() {
            Object value = parseValue();
            skipWs();
            return value;
        }
        private Object parseValue() {
            skipWs();
            char c = input.charAt(pos);
            if (c == '"') return parseString();
            if (c == '{') return parseObject();
            if (c == '[') return parseArray();
            if (c == 't') { expect("true"); return Boolean.TRUE; }
            if (c == 'f') { expect("false"); return Boolean.FALSE; }
            if (c == 'n') { expect("null"); return null; }
            return parseNumber();
        }
        private Map<String, Object> parseObject() {
            expect('{');
            Map<String, Object> out = new LinkedHashMap<>();
            skipWs();
            if (peek('}')) { pos++; return out; }
            while (true) {
                skipWs();
                String key = parseString();
                skipWs(); expect(':');
                out.put(key, parseValue());
                skipWs();
                if (peek('}')) { pos++; return out; }
                expect(',');
            }
        }
        private List<Object> parseArray() {
            expect('[');
            List<Object> out = new ArrayList<>();
            skipWs();
            if (peek(']')) { pos++; return out; }
            while (true) {
                out.add(parseValue());
                skipWs();
                if (peek(']')) { pos++; return out; }
                expect(',');
            }
        }
        private String parseString() {
            expect('"');
            StringBuilder sb = new StringBuilder();
            while (true) {
                char c = input.charAt(pos++);
                if (c == '"') return sb.toString();
                if (c != '\\') { sb.append(c); continue; }
                char e = input.charAt(pos++);
                switch (e) {
                    case '"': case '\\': case '/': sb.append(e); break;
                    case 'b': sb.append('\b'); break;
                    case 'f': sb.append('\f'); break;
                    case 'n': sb.append('\n'); break;
                    case 'r': sb.append('\r'); break;
                    case 't': sb.append('\t'); break;
                    case 'u':
                        String hex = input.substring(pos, pos + 4);
                        pos += 4;
                        sb.append((char) Integer.parseInt(hex, 16));
                        break;
                    default: throw new IllegalArgumentException("bad escape");
                }
            }
        }
        private Number parseNumber() {
            int start = pos;
            if (peek('-')) pos++;
            while (pos < input.length() && Character.isDigit(input.charAt(pos))) pos++;
            boolean floating = false;
            if (peek('.')) {
                floating = true; pos++;
                while (pos < input.length() && Character.isDigit(input.charAt(pos))) pos++;
            }
            if (peek('e') || peek('E')) {
                floating = true; pos++;
                if (peek('+') || peek('-')) pos++;
                while (pos < input.length() && Character.isDigit(input.charAt(pos))) pos++;
            }
            String raw = input.substring(start, pos);
            return floating ? Double.valueOf(raw) : Long.valueOf(raw);
        }
        private void expect(String s) {
            if (!input.startsWith(s, pos)) throw new IllegalArgumentException("expected " + s);
            pos += s.length();
        }
        private void expect(char c) {
            if (!peek(c)) throw new IllegalArgumentException("expected " + c);
            pos++;
        }
        private boolean peek(char c) { return pos < input.length() && input.charAt(pos) == c; }
        private void skipWs() {
            while (pos < input.length()) {
                char c = input.charAt(pos);
                if (c == ' ' || c == '\n' || c == '\r' || c == '\t') pos++;
                else break;
            }
        }
    }
}
