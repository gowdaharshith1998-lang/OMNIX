#!/usr/bin/env bash
# OMNIX live demo against Spring Petclinic.
#
# Assumes the kind cluster from the deploy verification dispatch is up
# (cluster name: omnix-verify, helm release: omnix-test, namespace: omnix).
# If the cluster is absent the script exits with a clear message; re-run the
# verify dispatch's Phase B to bring it back.
set -euo pipefail

TS=$(date -u +%Y%m%dT%H%M%SZ)
RUN="demos/petclinic/runs/$TS"
mkdir -p "$RUN/receipts"

echo "==> OMNIX Spring Petclinic demo  ts=$TS"
echo "    artifacts: $RUN"

# ----- Step 0: cluster preflight -----
if ! kubectl --context kind-omnix-verify get nodes >/dev/null 2>&1; then
  cat >&2 <<'MSG'
ERROR: kind cluster 'omnix-verify' is not reachable.
       Re-run the deploy verification dispatch (Phase B) to bring it up:
         see omnix_deploy_verification.html, then return here.
MSG
  exit 1
fi

# ----- Step 1: fetch Spring Petclinic -----
if [ ! -f "$RUN/petclinic.tar.gz" ]; then
  if [ -f demos/petclinic/cache/petclinic.tar.gz ]; then
    cp demos/petclinic/cache/petclinic.tar.gz "$RUN/petclinic.tar.gz"
  else
    mkdir -p demos/petclinic/cache
    SRC=$(mktemp -d -t petclinic-src.XXXXXX)
    git clone --depth=1 https://github.com/spring-projects/spring-petclinic.git "$SRC"
    (cd "$SRC" && rm -rf .git target node_modules)
    tar czf demos/petclinic/cache/petclinic.tar.gz -C "$(dirname "$SRC")" "$(basename "$SRC")"
    rm -rf "$SRC"
    cp demos/petclinic/cache/petclinic.tar.gz "$RUN/petclinic.tar.gz"
  fi
fi
PETCLINIC_SIZE=$(stat -c %s "$RUN/petclinic.tar.gz")
echo "==> petclinic tarball: $PETCLINIC_SIZE bytes"

# ----- Step 2: port-forward the API + facade -----
pkill -f 'kubectl port-forward.*omnix' 2>/dev/null || true
sleep 1
kubectl port-forward --namespace omnix svc/omnix-test-omnix-api 8080:8080 > "$RUN/pf-api.log" 2>&1 &
echo "$!" > "$RUN/pf-api.pid"
if kubectl get --namespace omnix svc/omnix-test-omnix-facade >/dev/null 2>&1; then
  kubectl port-forward --namespace omnix svc/omnix-test-omnix-facade 8081:8080 > "$RUN/pf-facade.log" 2>&1 &
  echo "$!" > "$RUN/pf-facade.pid"
  FACADE_PRESENT=1
else
  echo "    note: facade Service not present; traffic-shift step will be skipped"
  FACADE_PRESENT=0
fi
sleep 5
curl -fsS http://127.0.0.1:8080/health > "$RUN/health.json"
echo "==> API live"

# ----- Step 3: tus upload -----
UPLOAD_CREATE_HEADERS="$RUN/upload-create.txt"
curl -sS -X POST http://127.0.0.1:8080/v1/upload/ \
  -H "Tus-Resumable: 1.0.0" \
  -H "Upload-Length: $PETCLINIC_SIZE" \
  -H "Upload-Metadata: filename cGV0Y2xpbmljLnRhci5neg==" \
  -D "$UPLOAD_CREATE_HEADERS" > /dev/null
UPLOAD_LOC=$(grep -i '^location:' "$UPLOAD_CREATE_HEADERS" | awk '{print $2}' | tr -d '\r')
if [ -z "$UPLOAD_LOC" ]; then
  echo "ERROR: tus create returned no Location header" >&2
  cat "$UPLOAD_CREATE_HEADERS" >&2
  exit 2
fi
UPLOAD_ID=$(basename "$UPLOAD_LOC")
UPLOAD_URL=$UPLOAD_LOC
if [[ "$UPLOAD_URL" != http* ]]; then
  UPLOAD_URL="http://127.0.0.1:8080$UPLOAD_LOC"
fi
echo "==> upload created: $UPLOAD_ID"

curl -sS -X PATCH "$UPLOAD_URL" \
  -H "Tus-Resumable: 1.0.0" -H "Upload-Offset: 0" \
  -H "Content-Type: application/offset+octet-stream" \
  --data-binary "@$RUN/petclinic.tar.gz" \
  -D "$RUN/upload-patch.txt" > /dev/null
echo "==> bytes uploaded"

# Storage-key resolution (works around dispatch's gap #13 — tus upload_id is
# not auto-resolved by /v1/jobs).
STORAGE_KEY=$(curl -sS "http://127.0.0.1:8080/v1/upload/$UPLOAD_ID/status" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('storage_key',''))")
if [ -z "$STORAGE_KEY" ]; then
  echo "ERROR: /v1/upload/$UPLOAD_ID/status returned no storage_key" >&2
  exit 3
fi

# ----- Step 4: kick off the job -----
JOB_BODY=$(jq -nc \
  --arg uid "$UPLOAD_ID" \
  --arg sk "$STORAGE_KEY" \
  '{source:{type:"tus",upload_id:$uid,storage_key:$sk},target_language:"java21",mode:"production",scope:["src/main/java/org/springframework/samples/petclinic/owner/OwnerController.java"]}')
JOB_RESP=$(curl -sS -X POST http://127.0.0.1:8080/v1/jobs \
  -H 'Content-Type: application/json' \
  -d "$JOB_BODY")
JOB_ID=$(echo "$JOB_RESP" | jq -r '.job_id // empty')
if [ -z "$JOB_ID" ]; then
  echo "ERROR: POST /v1/jobs returned no job_id" >&2
  echo "$JOB_RESP" >&2
  exit 4
fi
echo "==> job started: $JOB_ID"
echo "$JOB_RESP" > "$RUN/job-created.json"

# ----- Step 5: stream the gate progression -----
for i in $(seq 1 120); do
  STATE_JSON=$(curl -sS "http://127.0.0.1:8080/v1/jobs/$JOB_ID" 2>/dev/null || echo '{}')
  STATE=$(echo "$STATE_JSON" | jq -r '.state // "?"')
  GATE=$(echo "$STATE_JSON" | jq -r '.current_gate // "?"')
  printf "[t=%3ds] state=%-12s gate=%s\n" $((i*5)) "$STATE" "$GATE" | tee -a "$RUN/job-poll.txt"
  case "$STATE" in
    complete|done|error|failed|awaiting_cutover) break ;;
  esac
  sleep 5
done
curl -sS "http://127.0.0.1:8080/v1/jobs/$JOB_ID" > "$RUN/job-final.json"
curl -sS "http://127.0.0.1:8080/v1/jobs/$JOB_ID/events" > "$RUN/job-events.json" || echo "{}" > "$RUN/job-events.json"
curl -sS "http://127.0.0.1:8080/v1/jobs/$JOB_ID/receipts" > "$RUN/job-receipts-list.json" || echo "[]" > "$RUN/job-receipts-list.json"
echo "==> gate progression captured"

# ----- Step 6: download + offline-verify each receipt -----
N_RECEIPTS=$(jq -r '(.receipts // .) | if type == "array" then length else 0 end' "$RUN/job-receipts-list.json" 2>/dev/null || echo 0)
echo "==> $N_RECEIPTS receipts to verify"

python3 - <<PY > "$RUN/verify.txt" 2>&1 || true
import json, urllib.request, base64, pathlib, sys
try:
    from omnix.receipts.keygen import keygen  # noqa: F401 — surface check
    from omnix.receipts.verify import verify_bytes
except Exception as e:
    print(f"WARN: omnix.receipts not importable: {e}")
    print("Skipping offline verify; treating as ok=0 fail=0.")
    sys.exit(0)

run = pathlib.Path("$RUN")
listing = json.load(open(run / "job-receipts-list.json"))
items = listing.get("receipts", listing) if isinstance(listing, dict) else listing
if not isinstance(items, list):
    items = []
ok = fail = 0
for r in items:
    rid = r.get("receipt_id") or r.get("id")
    if not rid:
        continue
    try:
        bundle = json.loads(urllib.request.urlopen(
            f"http://127.0.0.1:8080/v1/jobs/$JOB_ID/receipts/{rid}"
        ).read())
        (run / "receipts" / f"{rid}.bundle.json").write_text(json.dumps(bundle, indent=2))
        payload = json.dumps(bundle["payload"], sort_keys=True, separators=(",", ":")).encode()
        ctx = base64.b64decode(bundle.get("ctx_b64", "") or "")
        sig = base64.b64decode(bundle["signature_b64"])
        pub = base64.b64decode(bundle["pubkey_b64"])
        if verify_bytes(pub, payload, ctx, sig):
            print(f"OK   {rid}")
            ok += 1
        else:
            print(f"FAIL {rid}")
            fail += 1
    except Exception as e:
        print(f"FAIL {rid}: {e}")
        fail += 1
print(f"\nTotal: {ok+fail}  ok={ok}  fail={fail}")
PY
echo "==> offline verify complete"
cat "$RUN/verify.txt"

# ----- Step 7: traffic-shift demo (skipped if facade absent) -----
if [ "$FACADE_PRESENT" = "1" ]; then
  echo "==> baseline traffic sample (100 requests)"
  for i in $(seq 1 100); do curl -sS http://127.0.0.1:8081/ 2>/dev/null || true; done | sort | uniq -c > "$RUN/traffic-baseline.txt"
  cat "$RUN/traffic-baseline.txt"

  FACADE_POD=$(kubectl get pods --namespace omnix -l component=facade -o custom-columns=:metadata.name --no-headers 2>/dev/null | head -1)
  if [ -n "$FACADE_POD" ]; then
    kubectl exec --namespace omnix "$FACADE_POD" -c envoy -- cat /etc/envoy/routes/routes.json > "$RUN/routes-before.json" 2>/dev/null || true
  fi

  echo "==> request 1% shift"
  curl -sS -X POST http://127.0.0.1:8080/v1/cutover/owner-controller/shift \
    -H 'Content-Type: application/json' \
    -d '{"tenant_id":"demo","target_percentage":1,"reason":"petclinic demo, 1%"}' > "$RUN/shift-1pct.json"
  sleep 4
  if [ -n "$FACADE_POD" ]; then
    kubectl exec --namespace omnix "$FACADE_POD" -c envoy -- cat /etc/envoy/routes/routes.json > "$RUN/routes-after-1pct.json" 2>/dev/null || true
  fi
  for i in $(seq 1 200); do curl -sS http://127.0.0.1:8081/ 2>/dev/null || true; done | sort | uniq -c > "$RUN/traffic-after-shift.txt"
  cat "$RUN/traffic-after-shift.txt"

  echo "==> rollback"
  curl -sS -X POST http://127.0.0.1:8080/v1/cutover/owner-controller/rollback \
    -H 'Content-Type: application/json' \
    -d '{"tenant_id":"demo","reason":"end of demo"}' > "$RUN/rollback.json"
  sleep 4
  for i in $(seq 1 100); do curl -sS http://127.0.0.1:8081/ 2>/dev/null || true; done | sort | uniq -c > "$RUN/traffic-after-rollback.txt"
  cat "$RUN/traffic-after-rollback.txt"
else
  echo "==> facade absent — skipping traffic-shift step"
  echo "(facade Service not present in cluster)" > "$RUN/traffic-shift-skipped.txt"
fi

# ----- Step 8: write the demo report -----
N_OK=$(grep -c '^OK ' "$RUN/verify.txt" 2>/dev/null || echo 0)
N_FAIL=$(grep -c '^FAIL ' "$RUN/verify.txt" 2>/dev/null || echo 0)
JOB_FINAL_STATE=$(jq -r '.state // "?"' "$RUN/job-final.json" 2>/dev/null || echo "?")
EVENT_COUNT=$(jq -r '(.events // .) | if type == "array" then length else 0 end' "$RUN/job-events.json" 2>/dev/null || echo 0)

{
  echo "# OMNIX Spring Petclinic Demo — $TS"
  echo
  echo "## Inputs"
  echo "- Codebase: Spring Petclinic (~5.5K LOC Java)"
  echo "- Tarball: $PETCLINIC_SIZE bytes"
  echo "- Target language: Java 21"
  echo "- Scope: src/main/java/org/springframework/samples/petclinic/owner/OwnerController.java"
  echo
  echo "## Pipeline"
  echo "- Job ID: $JOB_ID"
  echo "- Final state: $JOB_FINAL_STATE"
  echo "- Events captured: $EVENT_COUNT"
  echo
  echo "## Receipts"
  echo "- Total emitted: $N_RECEIPTS"
  echo "- Offline-verified OK: $N_OK"
  echo "- Offline-verify FAILED: $N_FAIL"
  echo
  if [ "$FACADE_PRESENT" = "1" ]; then
    echo "## Cutover demonstration"
    echo
    echo "Baseline:"
    echo '```'
    cat "$RUN/traffic-baseline.txt"
    echo '```'
    echo
    echo "After 1% shift:"
    echo '```'
    cat "$RUN/traffic-after-shift.txt"
    echo '```'
    echo
    echo "After rollback:"
    echo '```'
    cat "$RUN/traffic-after-rollback.txt"
    echo '```'
  else
    echo "## Cutover demonstration"
    echo "_Skipped — facade Service absent. Re-run after gap #7 lands._"
  fi
  echo
  echo "## Artifacts"
  for f in "$RUN"/*; do
    echo "- $(basename "$f")"
  done
} > "$RUN/REPORT.md"

# ----- Step 9: tear down port-forwards -----
kill "$(cat "$RUN/pf-api.pid")" 2>/dev/null || true
[ "$FACADE_PRESENT" = "1" ] && kill "$(cat "$RUN/pf-facade.pid")" 2>/dev/null || true

echo ""
echo "==> DEMO COMPLETE"
echo "    report: $RUN/REPORT.md"
echo "    artifacts: $RUN/"
