/*
 * JavaSemanticEmitter — JavaParser-driven semantic emitter for OMNIX.
 *
 * Reads a Java source file + optional classpath entries; emits one JSON
 * object per declared method (and constructor) to stdout, matching the
 * SemanticNode schema consumed by `omnix.semantic.node.SemanticNode.from_json`.
 *
 * Exit codes:
 *   0  success
 *   2  UnsolvedSymbolException — first line of stderr is the well-known sentinel
 *      "UnresolvedSymbol: <symbol>@<file>:<line> :: <message>"
 *   1  any other error
 *
 * No third-party JSON dep — emits JSON by hand (one object per line) so the JAR
 * only depends on JavaParser core + symbol-solver + javassist.
 */

import com.github.javaparser.JavaParser;
import com.github.javaparser.ParseResult;
import com.github.javaparser.ParserConfiguration;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.Modifier;
import com.github.javaparser.ast.body.ConstructorDeclaration;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.body.Parameter;
import com.github.javaparser.ast.body.TypeDeclaration;
import com.github.javaparser.ast.expr.MethodCallExpr;
import com.github.javaparser.resolution.UnsolvedSymbolException;
import com.github.javaparser.resolution.declarations.ResolvedMethodDeclaration;
import com.github.javaparser.symbolsolver.JavaSymbolSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.CombinedTypeSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.JarTypeSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.JavaParserTypeSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.ReflectionTypeSolver;

import java.io.IOException;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;
import java.util.function.Supplier;

public final class JavaSemanticEmitter {

    private JavaSemanticEmitter() {}

    public static void main(String[] args) {
        if (args.length < 1) {
            System.err.println("usage: JavaSemanticEmitter <source.java> [<classpath-entry>...]");
            System.exit(1);
        }
        Path sourcePath = Paths.get(args[0]);
        List<Path> classpath = new ArrayList<>();
        for (int i = 1; i < args.length; i++) {
            classpath.add(Paths.get(args[i]));
        }
        try {
            run(sourcePath, classpath);
        } catch (UnsolvedSymbolException ex) {
            int line = 0;
            System.err.println(
                "UnresolvedSymbol: " + safeName(ex) + "@" + sourcePath + ":" + line
                    + " :: " + nullToEmpty(ex.getMessage())
            );
            System.exit(2);
        } catch (Throwable ex) {
            ex.printStackTrace(System.err);
            System.exit(1);
        }
    }

    static void run(Path sourcePath, List<Path> classpath) throws IOException {
        CombinedTypeSolver solver = new CombinedTypeSolver();
        solver.add(new ReflectionTypeSolver());
        Path parent = sourcePath.getParent();
        if (parent != null) {
            try {
                solver.add(new JavaParserTypeSolver(parent));
            } catch (Throwable ignored) {
                // best-effort source-dir solver
            }
        }
        for (Path cp : classpath) {
            try {
                solver.add(new JarTypeSolver(cp));
            } catch (Throwable ignored) {
                // skip unsupported classpath entries
            }
        }
        ParserConfiguration cfg = new ParserConfiguration()
            .setSymbolResolver(new JavaSymbolSolver(solver));
        JavaParser parser = new JavaParser(cfg);
        ParseResult<CompilationUnit> result = parser.parse(sourcePath);
        if (!result.isSuccessful() || result.getResult().isEmpty()) {
            System.err.println("parse failed: " + result.getProblems());
            System.exit(1);
            return;
        }
        CompilationUnit cu = result.getResult().get();
        String pkg = cu.getPackageDeclaration().map(p -> p.getNameAsString()).orElse("");

        for (TypeDeclaration<?> td : cu.getTypes()) {
            String typeName = td.getNameAsString();
            String typeFqn = pkg.isEmpty() ? typeName : pkg + "." + typeName;
            for (MethodDeclaration m : td.getMethods()) {
                emitMethod(m, typeFqn, sourcePath);
            }
            for (ConstructorDeclaration c : td.getConstructors()) {
                emitConstructor(c, typeFqn, sourcePath);
            }
        }
    }

    private static void emitMethod(MethodDeclaration m, String typeFqn, Path sourcePath) {
        String methodFqn = typeFqn + "." + m.getNameAsString();
        // R-3.3: return + parameter types must resolve. UnsolvedSymbolException
        // propagates to main() which emits the well-known sentinel + exit 2.
        // We do NOT silently fall back to the unresolved name here — that would
        // poison downstream gate logic with sentinel-typed signatures.
        String returnType = m.getType().resolve().describe();
        List<String> paramTypes = new ArrayList<>();
        for (Parameter p : m.getParameters()) {
            paramTypes.add(p.getType().resolve().describe());
        }
        String signature = buildMethodSignature(m, returnType, paramTypes);
        // Per-call dependency resolution KEEPS fallback — a single unresolvable
        // call site (e.g. dynamic dispatch JavaParser can't track) shouldn't
        // sink an otherwise-resolvable whole-file parse. The dep gets emitted
        // with its source-name FQN; downstream gate 4 surfaces the discrepancy.
        List<String[]> deps = collectDeps(m);
        int line = m.getRange().map(r -> r.begin.line).orElse(0);
        emitJson(methodFqn, "method", signature, paramTypes, returnType, deps,
            sourcePath.toString(), line, 0);
    }

    private static void emitConstructor(ConstructorDeclaration c, String typeFqn, Path sourcePath) {
        String methodFqn = typeFqn + "." + c.getNameAsString();
        List<String> paramTypes = new ArrayList<>();
        for (Parameter p : c.getParameters()) {
            paramTypes.add(p.getType().resolve().describe());
        }
        String signature = buildCtorSignature(c, paramTypes);
        int line = c.getRange().map(r -> r.begin.line).orElse(0);
        emitJson(methodFqn, "method", signature, paramTypes, null,
            new ArrayList<String[]>(), sourcePath.toString(), line, 0);
    }

    private static List<String[]> collectDeps(MethodDeclaration m) {
        List<String[]> deps = new ArrayList<>();
        m.findAll(MethodCallExpr.class).forEach(mc -> {
            String targetFqn;
            int callLine = mc.getRange().map(r -> r.begin.line).orElse(0);
            try {
                ResolvedMethodDeclaration resolved = mc.resolve();
                targetFqn = resolved.getQualifiedName();
            } catch (Throwable ex) {
                targetFqn = mc.getNameAsString();
            }
            deps.add(new String[]{targetFqn, "calls", String.valueOf(callLine)});
        });
        return deps;
    }

    private static String resolveOrFallback(Supplier<String> resolver, String fallback) {
        try {
            return resolver.get();
        } catch (Throwable ex) {
            return fallback;
        }
    }

    private static String buildMethodSignature(MethodDeclaration m, String returnType,
                                                List<String> paramTypes) {
        StringBuilder sb = new StringBuilder();
        for (Modifier mod : m.getModifiers()) {
            sb.append(mod.getKeyword().asString()).append(' ');
        }
        sb.append(returnType).append(' ');
        sb.append(m.getNameAsString()).append('(');
        sb.append(String.join(", ", paramTypes));
        sb.append(')');
        return sb.toString();
    }

    private static String buildCtorSignature(ConstructorDeclaration c, List<String> paramTypes) {
        StringBuilder sb = new StringBuilder();
        for (Modifier mod : c.getModifiers()) {
            sb.append(mod.getKeyword().asString()).append(' ');
        }
        sb.append(c.getNameAsString()).append('(');
        sb.append(String.join(", ", paramTypes));
        sb.append(')');
        return sb.toString();
    }

    private static void emitJson(String fqn, String kind, String signature, List<String> paramTypes,
                                  String returnType, List<String[]> deps, String filePath,
                                  int line, int column) {
        StringBuilder sb = new StringBuilder();
        sb.append('{');
        sb.append("\"fqn\":").append(jsonStr(fqn)).append(',');
        sb.append("\"kind\":").append(jsonStr(kind)).append(',');
        sb.append("\"signature\":").append(jsonStr(signature)).append(',');
        sb.append("\"resolved_param_types\":").append(jsonArr(paramTypes)).append(',');
        sb.append("\"resolved_return_type\":");
        if (returnType == null || "void".equals(returnType)) {
            sb.append("null");
        } else {
            sb.append(jsonStr(returnType));
        }
        sb.append(',');
        sb.append("\"dependency_edges\":[");
        for (int i = 0; i < deps.size(); i++) {
            String[] dep = deps.get(i);
            if (i > 0) sb.append(',');
            sb.append('{').append("\"target_fqn\":").append(jsonStr(dep[0])).append(',')
                .append("\"kind\":").append(jsonStr(dep[1])).append(',')
                .append("\"line\":").append(dep[2]).append('}');
        }
        sb.append("],");
        sb.append("\"source_location\":{")
            .append("\"file_path\":").append(jsonStr(filePath)).append(',')
            .append("\"line\":").append(line).append(',')
            .append("\"column\":").append(column).append('}');
        sb.append('}');
        System.out.println(sb.toString());
    }

    private static String jsonStr(String s) {
        if (s == null) return "null";
        StringBuilder sb = new StringBuilder("\"");
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '"':  sb.append("\\\""); break;
                case '\\': sb.append("\\\\"); break;
                case '\n': sb.append("\\n");  break;
                case '\r': sb.append("\\r");  break;
                case '\t': sb.append("\\t");  break;
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

    private static String jsonArr(List<String> items) {
        StringBuilder sb = new StringBuilder("[");
        for (int i = 0; i < items.size(); i++) {
            if (i > 0) sb.append(',');
            sb.append(jsonStr(items.get(i)));
        }
        sb.append(']');
        return sb.toString();
    }

    private static String nullToEmpty(String s) {
        return s == null ? "" : s;
    }

    private static String safeName(UnsolvedSymbolException ex) {
        try {
            return ex.getName();
        } catch (Throwable t) {
            return "unknown";
        }
    }
}
