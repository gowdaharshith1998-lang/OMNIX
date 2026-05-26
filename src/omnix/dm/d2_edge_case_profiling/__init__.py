"""D2 — AI Edge-Case Profiling.

Pipeline:
    probe_planner.plan(mappings, schema, ...)   -> ProbePlan
    probers/*.run(req, conn)                    -> ProbeResult
    manifest_emitter.emit(results, mid, pred)   -> Path  (signed JSON manifest)
"""
