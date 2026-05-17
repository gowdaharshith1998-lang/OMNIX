/*
 * JavaSemanticEmitter — JavaParser harness for OMNIX semantic layer (M1).
 *
 * Compile target: Java 21.
 * Dependencies (resolve & shade into javaparser-emitter.jar):
 *   - com.github.javaparser:javaparser-core
 *   - com.github.javaparser:javaparser-symbol-solver-core
 *
 * Contract with the Python bridge (src/omnix/semantic/java/parser.py):
 *   argv[0]    : source file path (UTF-8)
 *   argv[1..N] : classpath entries (JARs or directories) for symbol resolution
 *
 * Output:
 *   - stdout: one JSON object per declared symbol, matching SemanticNode schema:
 *       {
 *         "fqn": "org.apache.commons.lang.StringUtils.reverse",
 *         "kind": "method" | "class" | "field",
 *         "signature": "public static String reverse(String)",
 *         "resolved_param_types": ["java.lang.String"],
 *         "resolved_return_type": "java.lang.String" | null,
 *         "dependency_edges": [
 *           {"target_fqn": "java.lang.StringBuilder.reverse", "kind": "calls", "line": 17}
 *         ],
 *         "source_location": {"file_path": "...", "line": 12, "column": 5}
 *       }
 *
 * Error protocol:
 *   - UnsolvedSymbolException → stderr line:
 *       "UnresolvedSymbol: <symbol>@<file>:<line> :: <message>"
 *     then exit 2.
 *   - Any other Throwable → stderr message, exit 1.
 *   - Success → exit 0.
 *
 * NOTE: This file is the *contract* for whoever vendors the JAR. The
 * JavaParser API calls below are intentionally stubbed with TODO markers;
 * the file is not expected to compile until the dependencies are wired in
 * by scripts/vendor_javaparser.sh.
 */

import java.io.PrintStream;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;

public final class JavaSemanticEmitter {

    private JavaSemanticEmitter() {
        // utility class
    }

    public static void main(String[] args) {
        if (args.length < 1) {
            System.err.println("usage: java -jar javaparser-emitter.jar <source.java> [classpath...]");
            System.exit(1);
        }

        Path source = Paths.get(args[0]);
        List<Path> classpath = new ArrayList<>();
        for (int i = 1; i < args.length; i++) {
            classpath.add(Paths.get(args[i]));
        }

        try {
            run(source, classpath, System.out);
            System.exit(0);
        } catch (UnsolvedSymbolMarker u) {
            // Mirrors com.github.javaparser.resolution.UnsolvedSymbolException;
            // re-thrown via a local marker so the bridge contract is explicit.
            System.err.println(
                "UnresolvedSymbol: " + u.symbol + "@" + u.file + ":" + u.line + " :: " + u.message
            );
            System.exit(2);
        } catch (Throwable t) {
            t.printStackTrace(System.err);
            System.exit(1);
        }
    }

    /**
     * Drive the JavaParser symbol-solver against `source`, emitting one JSON
     * object per declared symbol to `out`.
     */
    private static void run(Path source, List<Path> classpath, PrintStream out) throws Exception {
        // TODO(m1-phase3-jvm): wire JavaParser API
        //   1. Build CombinedTypeSolver:
        //        - ReflectionTypeSolver (java.* / javax.*)
        //        - JavaParserTypeSolver(rootSourceDir)
        //        - JarTypeSolver per `classpath` entry
        //   2. Configure ParserConfiguration with JavaSymbolSolver(solver)
        //   3. StaticJavaParser.setConfiguration(config)
        //   4. CompilationUnit cu = StaticJavaParser.parse(source)
        //   5. cu.walk(TypeDeclaration.class, td -> emitType(td, source, out))
        //   6. cu.walk(MethodDeclaration.class, md -> emitMethod(md, source, out))
        //
        // emitType / emitMethod must:
        //   - resolve() each declaration → ResolvedTypeDeclaration / ResolvedMethodDeclaration
        //   - extract fqn (resolved.getQualifiedName())
        //   - extract signature (modifiers + return + name + param types)
        //   - resolved_param_types: walk parameters → resolve().describe()
        //   - resolved_return_type: resolved.getReturnType().describe() (null for void)
        //   - dependency_edges: walk MethodCallExpr in body, resolve() each,
        //     emit DependencyEdge{target_fqn, kind="calls", line=node.getBegin().line}
        //   - source_location: source path + getBegin() line/column
        //
        // Serialize via a minimal hand-rolled JSON writer (no Jackson dep) that
        // honors sorted-keys + compact separators to match SemanticNode.to_json.
        throw new UnsupportedOperationException(
            "JavaSemanticEmitter.run not implemented — see TODO(m1-phase3-jvm)"
        );
    }

    /**
     * Local marker used to translate
     * com.github.javaparser.resolution.UnsolvedSymbolException into the bridge
     * contract without leaking the JavaParser type up to main().
     */
    private static final class UnsolvedSymbolMarker extends RuntimeException {
        final String symbol;
        final String file;
        final int line;
        final String message;

        UnsolvedSymbolMarker(String symbol, String file, int line, String message) {
            super(message);
            this.symbol = symbol;
            this.file = file;
            this.line = line;
            this.message = message;
        }
    }
}
