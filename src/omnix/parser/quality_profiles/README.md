# Quality profiles

OMNIX can apply **per-grammar** quality scores for universal ingest (see
`src/omnix/parser/quality.py`: `compute_score_v2`).

## Schema

- **`src/omnix/parser/quality_profiles/<grammar>.json`** — declarative profile
  - `grammar` (string, must match the filename)
  - `formula`: `"weighted_sum"` or `"custom_python"`
  - `profile_version` (int, default `1`)
  - `weights` (object): node-type / signal → weight in `[0, 1]`; **sum of weights
    must be ≤ 1.0** (tolerance 0.01 for floating point)
  - `required_minimums` (object, optional): per-key minimum counts to unlock
    that weight’s bucket
  - `python_module` (string, optional): for `custom_python` in JSON, path to
    a `.py` file (defaults to adjacent `<grammar>.py`)

- **`src/omnix/parser/quality_profiles/<grammar>.py`** — escape hatch, **takes
  precedence** over a same-named `.json` file. Must define:

  `def score(stats: dict) -> float`

  where `stats` is derived from `omnix.parser.quality.QualityInputs` (and
  a few convenient derived keys such as `line_density`).

**Adding a new profile:** add `yourgrammar.json` and/or `yourgrammar.py` under
this directory; no Python changes are required in callers beyond wiring
`compute_score_v2(..., "yourgrammar")` if a new dispatch key is introduced.

## Profiles shipped

| File | Notes |
|------|--------|
| `python.json` | Matches legacy v1 five buckets (fn / import / call / names / line density) + same "all structure empty -> 0" short-circuit in `compute_score_v2`. |
| `typescript.json` | Same v1-style core + small interface / type / enum terms. |
| `javascript.json` | Arrow + class + module idiom; same empty short-circuit as v1. |
| `go.json`, `rust.json`, `java.json` | Syntactic stats from `parse_stats_for_universal_ingest`. |
| `generic.json` | Default when `load_profile(unknown)` (no per-language file). |

Calibration details live in `docs/QUALITY_PROFILE_BASELINES.md`. The
authoritative expected ranges are the `expected_range` blocks in each profile
JSON. Build trees such as `.next/` are excluded from `iter_dispatch_paths`
(see `src/omnix/find_bugs/walker.py` `IGNORE_DIRS`) so generated bundles do
not drag down grammar means.

## Validation

Invalid profiles raise :class:`QualityProfileValidationError` (with the file path
in the message). The loader does **not** fall back to the legacy score when
validation fails.
