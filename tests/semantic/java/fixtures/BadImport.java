package broken;

// Deliberately unresolvable: NotARealPackage is not in any standard classpath
// AND not in any fixture-provided classpath. Triggers the symbol-solver's
// UnsolvedSymbolException path on the method signature, which the emitter
// converts to the well-known "UnresolvedSymbol:" stderr sentinel + exit 2.
// Used by tests/semantic/java/test_parse_file.py::test_unresolved_symbol_raises_structured_error
// to validate R-3.3 (unresolved symbols are loud, not silent fallback).
import com.nonexistent.NotARealPackage;

public class BadImport {
    public static NotARealPackage missing(NotARealPackage in) {
        return in;
    }
}
