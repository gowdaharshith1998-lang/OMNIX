#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCS="$ROOT/docs"

PASSED="$DOCS/m2_demo_receipt_sample_passed.json"
FAILED="$DOCS/m2_demo_receipt_sample_failed.json"
CAST="$DOCS/m2_demo.cast"

if [[ ! -f "$PASSED" || ! -f "$FAILED" ]]; then
  cat >&2 <<'MSG'
Missing M2 demo receipt samples.

Run the operator live rebuild from docs/m2_live_run_protocol.md, then copy:
  docs/m2_demo_receipt_sample_passed.json
  docs/m2_demo_receipt_sample_failed.json
MSG
  exit 1
fi

echo "M2 demo receipt samples"
echo "passed: $PASSED"
echo "failed: $FAILED"
echo

python - "$PASSED" "$FAILED" <<'PY'
import json
import sys
from pathlib import Path

for raw in sys.argv[1:]:
    path = Path(raw)
    receipt = json.loads(path.read_text(encoding="utf-8"))
    gate6 = next(g for g in receipt.get("gate_results", []) if g.get("gate_number") == 6)
    print(f"{path.name}: {receipt.get('node_fqn')} gate6: {gate6.get('status')}")
    if gate6.get("status") == "failed":
        print(json.dumps({"diverging_input": gate6.get("details", {}).get("diverging_input")}))
PY

echo
echo "If this is an off-camera rehearsal after recording, validate the cast:"
echo "python scripts/validate_m2_demo_assets.py ."

if [[ -f "$CAST" ]]; then
  python "$ROOT/scripts/validate_m2_demo_assets.py" "$ROOT"
else
  echo "docs/m2_demo.cast is not present yet."
fi
