"""D1 — AI Schema Understanding.

Pipeline (top → bottom):
    ddl_parser.parse(ddl, dialect)              -> SchemaSpec | ParseFailure
    column_metadata.extract(schema, conn)       -> tuple[ColumnContext, ...]
    codebase_memory_bridge.lookup_column_usage  -> tuple[CodebasePathUsage, ...]
    column_embedder.embed(ctx)                  -> np.ndarray  (384,)
    semantic_matcher.match(legacy, target)      -> tuple[ColumnMapping, ...]
    mapping_emitter.emit(mappings, ...)         -> Path  (signed JSON manifest)
"""
