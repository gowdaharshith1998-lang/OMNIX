/*
 * JavaEquivalenceHarness - JVM-side harness for OMNIX gate 5.
 *
 * Reads one JSON object from stdin:
 *   {
 *     "legacy_source": "...",
 *     "rebuilt_source": "...",
 *     "class_name": "pkg.Type",
 *     "method_name": "method",
 *     "parameter_types": ["java.lang.String"],
 *     "cases": [["abc"], [""]]
 *   }
 *
 * Compiles legacy and rebuilt sources in isolated in-memory classloaders,
 * invokes the target method for each case, and emits one JSON object per case
 * plus a final {"__END__":true,"cases":N} sentinel.
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
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public final class JavaEquivalenceHarness {
    private JavaEquivalenceHarness() {}

    public static void main(String[] args) {
        try {
            String input = readAll();
            Object parsed = new JsonParser(input).parse();
            if (!(parsed instanceof Map)) {
                throw new IllegalArgumentException("top-level JSON must be an object");
            }
            @SuppressWarnings("unchecked")
            Map<String, Object> payload = (Map<String, Object>) parsed;
            run(payload);
        } catch (Throwable ex) {
            ex.printStackTrace(System.err);
            System.exit(1);
        }
    }

    private static void run(Map<String, Object> payload) throws Exception {
        String legacySource = requireString(payload, "legacy_source");
        String rebuiltSource = requireString(payload, "rebuilt_source");
        String className = requireString(payload, "class_name");
        String methodName = requireString(payload, "method_name");
        List<String> parameterTypes = requireStringList(payload, "parameter_types");
        List<Object> cases = requireList(payload, "cases");

        ClassLoader legacyLoader = compile(className, legacySource, "legacy");
        ClassLoader rebuiltLoader = compile(className, rebuiltSource, "rebuilt");
        Class<?> legacyClass = legacyLoader.loadClass(className);
        Class<?> rebuiltClass = rebuiltLoader.loadClass(className);
        Method legacyMethod = findMethod(legacyClass, methodName, parameterTypes);
        Method rebuiltMethod = findMethod(rebuiltClass, methodName, parameterTypes);

        int index = 0;
        for (Object rawCase : cases) {
            if (!(rawCase instanceof List)) {
                throw new IllegalArgumentException("case " + index + " must be an array");
            }
            @SuppressWarnings("unchecked")
            List<Object> caseValues = (List<Object>) rawCase;
            Object[] legacyArgs = convertArgs(caseValues, legacyMethod.getParameterTypes());
            Object[] rebuiltArgs = convertArgs(caseValues, rebuiltMethod.getParameterTypes());
            Outcome legacy = invoke(legacyClass, legacyMethod, legacyArgs);
            Outcome rebuilt = invoke(rebuiltClass, rebuiltMethod, rebuiltArgs);
            Comparison comparison = compareOutcomes(legacy, rebuilt);
            Map<String, Object> out = new LinkedHashMap<>();
            out.put("case_index", index);
            out.put("input", caseValues);
            out.put("legacy", legacy.toJson());
            out.put("rebuilt", rebuilt.toJson());
            out.put("equivalent", comparison.equivalent);
            out.put("divergence", comparison.divergence);
            System.out.println(toJson(out));
            index++;
        }
        Map<String, Object> end = new LinkedHashMap<>();
        end.put("__END__", true);
        end.put("cases", index);
        System.out.println(toJson(end));
    }

    private static ClassLoader compile(String className, String source, String label) {
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
        List<String> options = Arrays.asList("-classpath", System.getProperty("java.class.path", ""));
        Boolean ok = compiler.getTask(
            null,
            manager,
            diagnostics,
            options,
            null,
            Arrays.asList(sourceObject)
        ).call();
        if (!Boolean.TRUE.equals(ok)) {
            StringBuilder sb = new StringBuilder();
            sb.append(label).append(" compile failed");
            for (Diagnostic<? extends JavaFileObject> d : diagnostics.getDiagnostics()) {
                sb.append("\n")
                    .append(d.getKind())
                    .append(" line ")
                    .append(d.getLineNumber())
                    .append(": ")
                    .append(d.getMessage(null));
            }
            throw new IllegalArgumentException(sb.toString());
        }
        return new MemoryClassLoader(manager.classBytes());
    }

    private static Method findMethod(
        Class<?> clazz,
        String methodName,
        List<String> parameterTypes
    ) throws NoSuchMethodException {
        for (Method method : clazz.getDeclaredMethods()) {
            if (!method.getName().equals(methodName)) {
                continue;
            }
            if (method.getParameterCount() != parameterTypes.size()) {
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
        throw new NoSuchMethodException(
            clazz.getName() + "." + methodName + "(" + String.join(", ", parameterTypes) + ")"
        );
    }

    private static boolean typeMatches(Class<?> actual, String expected) {
        if (actual.isArray()) {
            return (actual.getComponentType().getName() + "[]").equals(expected)
                || actual.getName().equals(expected);
        }
        if (actual.isPrimitive()) {
            return actual.getName().equals(expected);
        }
        return actual.getName().equals(expected);
    }

    private static Object[] convertArgs(List<Object> values, Class<?>[] parameterTypes) {
        if (values.size() != parameterTypes.length) {
            throw new IllegalArgumentException(
                "case arity " + values.size() + " does not match method arity " + parameterTypes.length
            );
        }
        Object[] out = new Object[values.size()];
        for (int i = 0; i < values.size(); i++) {
            out[i] = convertValue(values.get(i), parameterTypes[i]);
        }
        return out;
    }

    private static Object convertValue(Object value, Class<?> targetType) {
        if (value == null) {
            return null;
        }
        if (targetType == String.class) {
            return String.valueOf(value);
        }
        if (targetType == char.class || targetType == Character.class) {
            String s = String.valueOf(value);
            return s.isEmpty() ? Character.valueOf('\0') : Character.valueOf(s.charAt(0));
        }
        if (targetType == boolean.class || targetType == Boolean.class) {
            return (Boolean) value;
        }
        if (targetType == byte.class || targetType == Byte.class) {
            return Byte.valueOf(((Number) value).byteValue());
        }
        if (targetType == short.class || targetType == Short.class) {
            return Short.valueOf(((Number) value).shortValue());
        }
        if (targetType == int.class || targetType == Integer.class) {
            return Integer.valueOf(((Number) value).intValue());
        }
        if (targetType == long.class || targetType == Long.class) {
            return Long.valueOf(((Number) value).longValue());
        }
        if (targetType == float.class || targetType == Float.class) {
            return Float.valueOf(((Number) value).floatValue());
        }
        if (targetType == double.class || targetType == Double.class) {
            return Double.valueOf(((Number) value).doubleValue());
        }
        if (targetType.isArray()) {
            if (!(value instanceof List)) {
                throw new IllegalArgumentException("array parameter requires JSON array");
            }
            @SuppressWarnings("unchecked")
            List<Object> rawList = (List<Object>) value;
            Class<?> component = targetType.getComponentType();
            Object array = Array.newInstance(component, rawList.size());
            for (int i = 0; i < rawList.size(); i++) {
                Array.set(array, i, convertValue(rawList.get(i), component));
            }
            return array;
        }
        if (List.class.isAssignableFrom(targetType)) {
            if (!(value instanceof List)) {
                throw new IllegalArgumentException("List parameter requires JSON array");
            }
            return new ArrayList<>((List<?>) value);
        }
        if (Set.class.isAssignableFrom(targetType)) {
            if (!(value instanceof List)) {
                throw new IllegalArgumentException("Set parameter requires JSON array");
            }
            return new LinkedHashSet<>((List<?>) value);
        }
        return value;
    }

    private static Outcome invoke(Class<?> clazz, Method method, Object[] args) {
        PrintStream oldOut = System.out;
        PrintStream oldErr = System.err;
        ByteArrayOutputStream sinkOut = new ByteArrayOutputStream();
        ByteArrayOutputStream sinkErr = new ByteArrayOutputStream();
        try {
            System.setOut(new PrintStream(sinkOut, true, StandardCharsets.UTF_8));
            System.setErr(new PrintStream(sinkErr, true, StandardCharsets.UTF_8));
            Object receiver = null;
            if (!Modifier.isStatic(method.getModifiers())) {
                Constructor<?> ctor = clazz.getDeclaredConstructor();
                ctor.setAccessible(true);
                receiver = ctor.newInstance();
            }
            Object value = method.invoke(receiver, args);
            return Outcome.returned(value);
        } catch (InvocationTargetException ex) {
            return Outcome.threw(ex.getTargetException());
        } catch (Throwable ex) {
            return Outcome.threw(ex);
        } finally {
            System.setOut(oldOut);
            System.setErr(oldErr);
        }
    }

    private static Comparison compareOutcomes(Outcome legacy, Outcome rebuilt) {
        if (legacy.exception != null || rebuilt.exception != null) {
            if (legacy.exception == null || rebuilt.exception == null) {
                return Comparison.different("exception_presence");
            }
            if (!legacy.exception.equals(rebuilt.exception)) {
                return Comparison.different("exception_type");
            }
            return Comparison.same();
        }
        if (valuesEqual(legacy.returnValue, rebuilt.returnValue)) {
            return Comparison.same();
        }
        return Comparison.different("return_value");
    }

    private static boolean valuesEqual(Object a, Object b) {
        if (a == b) {
            return true;
        }
        if (a == null || b == null) {
            return false;
        }
        if (a instanceof Double && b instanceof Double) {
            return Double.compare((Double) a, (Double) b) == 0;
        }
        if (a instanceof Float && b instanceof Float) {
            return Float.compare((Float) a, (Float) b) == 0;
        }
        Class<?> ac = a.getClass();
        Class<?> bc = b.getClass();
        if (ac.isArray() && bc.isArray()) {
            if (a instanceof byte[] && b instanceof byte[]) {
                return Arrays.equals((byte[]) a, (byte[]) b);
            }
            if (a instanceof short[] && b instanceof short[]) {
                return Arrays.equals((short[]) a, (short[]) b);
            }
            if (a instanceof int[] && b instanceof int[]) {
                return Arrays.equals((int[]) a, (int[]) b);
            }
            if (a instanceof long[] && b instanceof long[]) {
                return Arrays.equals((long[]) a, (long[]) b);
            }
            if (a instanceof float[] && b instanceof float[]) {
                return Arrays.equals((float[]) a, (float[]) b);
            }
            if (a instanceof double[] && b instanceof double[]) {
                return Arrays.equals((double[]) a, (double[]) b);
            }
            if (a instanceof char[] && b instanceof char[]) {
                return Arrays.equals((char[]) a, (char[]) b);
            }
            if (a instanceof boolean[] && b instanceof boolean[]) {
                return Arrays.equals((boolean[]) a, (boolean[]) b);
            }
            return Arrays.deepEquals((Object[]) a, (Object[]) b);
        }
        return Objects.equals(a, b);
    }

    private static String readAll() throws IOException {
        StringBuilder sb = new StringBuilder();
        char[] buf = new char[8192];
        try (Reader reader = new InputStreamReader(System.in, StandardCharsets.UTF_8)) {
            int n;
            while ((n = reader.read(buf)) != -1) {
                sb.append(buf, 0, n);
            }
        }
        return sb.toString();
    }

    private static String requireString(Map<String, Object> payload, String key) {
        Object value = payload.get(key);
        if (!(value instanceof String)) {
            throw new IllegalArgumentException("missing string key: " + key);
        }
        return (String) value;
    }

    private static List<String> requireStringList(Map<String, Object> payload, String key) {
        List<Object> raw = requireList(payload, key);
        List<String> out = new ArrayList<>();
        for (Object value : raw) {
            if (!(value instanceof String)) {
                throw new IllegalArgumentException("key " + key + " must be a string array");
            }
            out.add((String) value);
        }
        return out;
    }

    private static List<Object> requireList(Map<String, Object> payload, String key) {
        Object value = payload.get(key);
        if (!(value instanceof List)) {
            throw new IllegalArgumentException("missing array key: " + key);
        }
        @SuppressWarnings("unchecked")
        List<Object> list = (List<Object>) value;
        return list;
    }

    private static Object jsonValue(Object value) {
        if (value == null || value instanceof String || value instanceof Number || value instanceof Boolean) {
            return value;
        }
        Class<?> c = value.getClass();
        if (c.isArray()) {
            int n = Array.getLength(value);
            List<Object> out = new ArrayList<>(n);
            for (int i = 0; i < n; i++) {
                out.add(jsonValue(Array.get(value, i)));
            }
            return out;
        }
        return String.valueOf(value);
    }

    private static String toJson(Object value) {
        if (value == null) {
            return "null";
        }
        if (value instanceof String) {
            return jsonString((String) value);
        }
        if (value instanceof Number || value instanceof Boolean) {
            return String.valueOf(value);
        }
        if (value instanceof Map) {
            StringBuilder sb = new StringBuilder();
            sb.append('{');
            boolean first = true;
            for (Map.Entry<?, ?> entry : ((Map<?, ?>) value).entrySet()) {
                if (!first) {
                    sb.append(',');
                }
                first = false;
                sb.append(jsonString(String.valueOf(entry.getKey())));
                sb.append(':');
                sb.append(toJson(entry.getValue()));
            }
            sb.append('}');
            return sb.toString();
        }
        if (value instanceof Iterable) {
            StringBuilder sb = new StringBuilder();
            sb.append('[');
            boolean first = true;
            for (Object item : (Iterable<?>) value) {
                if (!first) {
                    sb.append(',');
                }
                first = false;
                sb.append(toJson(item));
            }
            sb.append(']');
            return sb.toString();
        }
        return jsonString(String.valueOf(value));
    }

    private static String jsonString(String s) {
        StringBuilder sb = new StringBuilder("\"");
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '"':
                    sb.append("\\\"");
                    break;
                case '\\':
                    sb.append("\\\\");
                    break;
                case '\b':
                    sb.append("\\b");
                    break;
                case '\f':
                    sb.append("\\f");
                    break;
                case '\n':
                    sb.append("\\n");
                    break;
                case '\r':
                    sb.append("\\r");
                    break;
                case '\t':
                    sb.append("\\t");
                    break;
                default:
                    if (c < 0x20) {
                        sb.append(String.format("\\u%04x", (int) c));
                    } else {
                        sb.append(c);
                    }
            }
        }
        sb.append('"');
        return sb.toString();
    }

    private static final class Outcome {
        final Object returnValue;
        final String exception;

        private Outcome(Object returnValue, String exception) {
            this.returnValue = returnValue;
            this.exception = exception;
        }

        static Outcome returned(Object value) {
            return new Outcome(value, null);
        }

        static Outcome threw(Throwable throwable) {
            return new Outcome(null, throwable.getClass().getName());
        }

        Map<String, Object> toJson() {
            Map<String, Object> out = new LinkedHashMap<>();
            out.put("return_value", jsonValue(returnValue));
            out.put("exception", exception);
            return out;
        }
    }

    private static final class Comparison {
        final boolean equivalent;
        final String divergence;

        private Comparison(boolean equivalent, String divergence) {
            this.equivalent = equivalent;
            this.divergence = divergence;
        }

        static Comparison same() {
            return new Comparison(true, null);
        }

        static Comparison different(String divergence) {
            return new Comparison(false, divergence);
        }
    }

    private static final class SourceFileObject extends SimpleJavaFileObject {
        private final String source;

        SourceFileObject(String className, String source) {
            super(URI.create("string:///" + className.replace('.', '/') + Kind.SOURCE.extension), Kind.SOURCE);
            this.source = source;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return source;
        }
    }

    private static final class ByteCodeFileObject extends SimpleJavaFileObject {
        private final ByteArrayOutputStream out = new ByteArrayOutputStream();

        ByteCodeFileObject(String className, Kind kind) {
            super(URI.create("bytes:///" + className.replace('.', '/') + kind.extension), kind);
        }

        @Override
        public ByteArrayOutputStream openOutputStream() {
            return out;
        }

        byte[] bytes() {
            return out.toByteArray();
        }
    }

    private static final class MemoryFileManager extends ForwardingJavaFileManager<JavaFileManager> {
        private final Map<String, ByteCodeFileObject> compiled = new LinkedHashMap<>();

        MemoryFileManager(JavaFileManager fileManager) {
            super(fileManager);
        }

        @Override
        public JavaFileObject getJavaFileForOutput(
            Location location,
            String className,
            JavaFileObject.Kind kind,
            FileObject sibling
        ) {
            ByteCodeFileObject file = new ByteCodeFileObject(className, kind);
            compiled.put(className, file);
            return file;
        }

        Map<String, byte[]> classBytes() {
            Map<String, byte[]> out = new LinkedHashMap<>();
            for (Map.Entry<String, ByteCodeFileObject> entry : compiled.entrySet()) {
                out.put(entry.getKey(), entry.getValue().bytes());
            }
            return out;
        }
    }

    private static final class MemoryClassLoader extends ClassLoader {
        private final Map<String, byte[]> classes;

        MemoryClassLoader(Map<String, byte[]> classes) {
            super(JavaEquivalenceHarness.class.getClassLoader());
            this.classes = classes;
        }

        @Override
        protected Class<?> findClass(String name) throws ClassNotFoundException {
            byte[] bytes = classes.get(name);
            if (bytes == null) {
                throw new ClassNotFoundException(name);
            }
            return defineClass(name, bytes, 0, bytes.length);
        }
    }

    private static final class JsonParser {
        private final String input;
        private int pos = 0;

        JsonParser(String input) {
            this.input = input;
        }

        Object parse() {
            Object value = parseValue();
            skipWs();
            if (pos != input.length()) {
                throw error("trailing data");
            }
            return value;
        }

        private Object parseValue() {
            skipWs();
            if (pos >= input.length()) {
                throw error("unexpected end");
            }
            char c = input.charAt(pos);
            if (c == '"') {
                return parseString();
            }
            if (c == '{') {
                return parseObject();
            }
            if (c == '[') {
                return parseArray();
            }
            if (c == 't') {
                expect("true");
                return Boolean.TRUE;
            }
            if (c == 'f') {
                expect("false");
                return Boolean.FALSE;
            }
            if (c == 'n') {
                expect("null");
                return null;
            }
            if (c == '-' || Character.isDigit(c)) {
                return parseNumber();
            }
            throw error("unexpected char: " + c);
        }

        private Map<String, Object> parseObject() {
            expect('{');
            Map<String, Object> out = new LinkedHashMap<>();
            skipWs();
            if (peek('}')) {
                pos++;
                return out;
            }
            while (true) {
                skipWs();
                String key = parseString();
                skipWs();
                expect(':');
                out.put(key, parseValue());
                skipWs();
                if (peek('}')) {
                    pos++;
                    return out;
                }
                expect(',');
            }
        }

        private List<Object> parseArray() {
            expect('[');
            List<Object> out = new ArrayList<>();
            skipWs();
            if (peek(']')) {
                pos++;
                return out;
            }
            while (true) {
                out.add(parseValue());
                skipWs();
                if (peek(']')) {
                    pos++;
                    return out;
                }
                expect(',');
            }
        }

        private String parseString() {
            expect('"');
            StringBuilder sb = new StringBuilder();
            while (pos < input.length()) {
                char c = input.charAt(pos++);
                if (c == '"') {
                    return sb.toString();
                }
                if (c != '\\') {
                    sb.append(c);
                    continue;
                }
                if (pos >= input.length()) {
                    throw error("unterminated escape");
                }
                char e = input.charAt(pos++);
                switch (e) {
                    case '"':
                    case '\\':
                    case '/':
                        sb.append(e);
                        break;
                    case 'b':
                        sb.append('\b');
                        break;
                    case 'f':
                        sb.append('\f');
                        break;
                    case 'n':
                        sb.append('\n');
                        break;
                    case 'r':
                        sb.append('\r');
                        break;
                    case 't':
                        sb.append('\t');
                        break;
                    case 'u':
                        if (pos + 4 > input.length()) {
                            throw error("short unicode escape");
                        }
                        String hex = input.substring(pos, pos + 4);
                        pos += 4;
                        sb.append((char) Integer.parseInt(hex, 16));
                        break;
                    default:
                        throw error("bad escape: " + e);
                }
            }
            throw error("unterminated string");
        }

        private Number parseNumber() {
            int start = pos;
            if (peek('-')) {
                pos++;
            }
            while (pos < input.length() && Character.isDigit(input.charAt(pos))) {
                pos++;
            }
            boolean floating = false;
            if (peek('.')) {
                floating = true;
                pos++;
                while (pos < input.length() && Character.isDigit(input.charAt(pos))) {
                    pos++;
                }
            }
            if (peek('e') || peek('E')) {
                floating = true;
                pos++;
                if (peek('+') || peek('-')) {
                    pos++;
                }
                while (pos < input.length() && Character.isDigit(input.charAt(pos))) {
                    pos++;
                }
            }
            String raw = input.substring(start, pos);
            return floating ? Double.valueOf(raw) : Long.valueOf(raw);
        }

        private void expect(String literal) {
            if (!input.startsWith(literal, pos)) {
                throw error("expected " + literal);
            }
            pos += literal.length();
        }

        private void expect(char c) {
            if (!peek(c)) {
                throw error("expected " + c);
            }
            pos++;
        }

        private boolean peek(char c) {
            return pos < input.length() && input.charAt(pos) == c;
        }

        private void skipWs() {
            while (pos < input.length()) {
                char c = input.charAt(pos);
                if (c == ' ' || c == '\n' || c == '\r' || c == '\t') {
                    pos++;
                } else {
                    break;
                }
            }
        }

        private IllegalArgumentException error(String message) {
            return new IllegalArgumentException(message + " at byte " + pos);
        }
    }
}
