#!/usr/bin/env bash
set -euo pipefail

pkill -f "omnix.*7777" 2>/dev/null || true
pkill -f "uvicorn.*7777" 2>/dev/null || true

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

export OMNIX_HOME="$(pwd)"

ts="$(date -u +%Y%m%dT%H%M%SZ)"
receipts_root=".omnix/receipts/cobol/${ts}"
mkdir -p "${receipts_root}"

fixtures_dir="tests/fixtures/cobol/nist/inputs"
run_fixtures=".omnix/tmp_cobol_fixtures_${ts}"
programs=(TC011A TC012A TC101M TC201C TC301E TC401P)
export OMNIX_COBOL_RECEIPTS_DIR="${receipts_root}"
export COBCPY="$(pwd)/tests/fixtures/cobol/nist/copybooks${COBCPY:+:${COBCPY}}"

fail() {
  echo "FAIL: program=$1 stage=$2 detail=$3" >&2
  exit 1
}

run_ingest_batch() {
  export OMNIX_INGEST_WORKERS=1
  python - <<'PY'
from pathlib import Path
from omnix.graph.store import GraphStore
from omnix.parser.ingest_dispatch import ingest_unified_codebase

root = Path(".").resolve()
db_dir = root / ".omnix"
db_dir.mkdir(parents=True, exist_ok=True)
store = GraphStore(str(db_dir / "omnix.db"))
ingest_unified_codebase(str(root), store)
store.close()
PY
}

echo "== batch ingest =="
run_ingest_batch || fail "GLOBAL" "ingest" "ingest_unified_codebase failed"

rm -rf "${run_fixtures}"
mkdir -p "${run_fixtures}"

verified_count=0
for p in "${programs[@]}"; do
  cob="tests/fixtures/cobol/nist/${p}.cob"
  rm -rf "${run_fixtures:?}/"*
  src="${fixtures_dir}/${p}.in"
  dst_dir="${run_fixtures}/${p}"
  mkdir -p "${dst_dir}"
  if [ -f "${src}" ]; then
    cp "${src}" "${dst_dir}/input.bin"
  else
    : > "${dst_dir}/input.bin"
  fi

  echo "== ${p}: capture =="
  rm -rf ".omnix/captures/cobol/${p}"
  python omnix.py cobol capture "${cob}" --fixtures "${run_fixtures}" || fail "${p}" "capture" "cobol capture failed"

  # cli_cobol spec-gen currently keys captures by program stem, not file path.
  echo "== ${p}: spec-gen =="
  python omnix.py cobol spec-gen "${p}" || fail "${p}" "spec-gen" "cobol spec-gen failed"

  echo "== ${p}: rebuild (gate pipeline) =="
  if ! python omnix.py cobol rebuild . --target python --node-filter "*${p}*"; then
    fail "${p}" "rebuild" "rebuild failed (precondition or gate failure)"
  fi

  receipt="${receipts_root}/${p}.json"
  [ -f "${receipt}" ] || fail "${p}" "receipt-discovery" "no COBOL rebuild receipt emitted at ${receipt}"

  echo "== ${p}: verify-rebuild =="
  python omnix.py axiom verify-rebuild "${receipt}" || fail "${p}" "verify-rebuild" "signature verification failed"

  gate_diag="$(python - <<PY
import json
from pathlib import Path
r = Path("${receipt}")
d = json.loads(r.read_text(encoding="utf-8"))
fails = []
for g in d.get("gate_results", []):
    n = g.get("gate_number")
    s = g.get("status")
    if s != "passed":
        fails.append(f"G{n}:{s}")
print(",".join(fails))
PY
)"
  if [ -n "${gate_diag}" ]; then
    fail "${p}" "gate-check" "${gate_diag}"
  fi
  verified_count=$((verified_count + 1))
done

if [ "${verified_count}" -ne 6 ]; then
  fail "GLOBAL" "finalize" "expected 6 verified receipts, got ${verified_count}"
fi

echo "SUCCESS: verified ${verified_count}/6 COBOL rebuild receipts at ${receipts_root}"
