#!/usr/bin/env bash
# M1 demo rehearsal — runs the full pipeline end-to-end against a scratch
# tmp workspace built from tests/corpus/commons_lang/. Use this to rehearse
# until you can hit the flow cleanly, then wrap a real asciinema rec
# around it for the canonical recording. See docs/M1_DEMO.md for the
# operator's recording protocol.
#
# Pre-flight (do these OFF-camera before recording):
#   - bash src/omnix/semantic/java/jvm/build.sh     # emitter JAR built
#   - omnix axiom keygen --project .                # project Ed25519 key
#   - register an Anthropic key in the Provider Fabric vault (BYOK UI)
#
# This script makes real LLM calls. Budget: <90s wall-clock, ~$0.05-$0.50.
# Cached responses are NOT used — every run is fresh.

set -euo pipefail

# Resolve repo root so this script works from any cwd
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

SCRATCH_DIR="${OMNIX_DEMO_DIR:-/tmp/omnix-m1-demo}"
NODE_FILTER="${OMNIX_DEMO_NODE_FILTER:-*StringUtils.reverse}"
MODEL="${OMNIX_DEMO_MODEL:-claude-opus-4.7}"
PUBKEY="${OMNIX_DEMO_PUBKEY:-${SCRATCH_DIR}/.omnix/pubkey.pem}"

# Off-camera setup
rm -rf "${SCRATCH_DIR}"
mkdir -p "${SCRATCH_DIR}"
cp -r "${REPO_ROOT}/tests/corpus/commons_lang/StringUtils.java" "${SCRATCH_DIR}/"

# Project keypair under SCRATCH_DIR so we don't pollute the user's repo
(
    cd "${SCRATCH_DIR}"
    omnix axiom keygen --project . > /dev/null
)

clear
echo "=== OMNIX M1 demo — Java 6 → Java 21 rebuild + signed receipt ==="
echo ""
echo "Workspace: ${SCRATCH_DIR}"
echo "Corpus:    Apache Commons Lang 2.6 StringUtils.reverse (Apache 2.0)"
echo "Model:     ${MODEL}"
echo ""

cd "${SCRATCH_DIR}"

echo "→ omnix analyze ."
omnix analyze --no-browser . &
ANALYZE_PID=$!
# analyze starts the studio server; give it a moment to populate the graph
sleep 5
# Kill the studio server cleanly so the demo continues
kill -INT ${ANALYZE_PID} 2>/dev/null || true
wait ${ANALYZE_PID} 2>/dev/null || true
echo ""

echo "→ omnix rebuild . --target java21 --node-filter '${NODE_FILTER}'"
omnix rebuild . --target java21 --node-filter "${NODE_FILTER}" --model "${MODEL}"
echo ""

RECEIPT=$(ls "${SCRATCH_DIR}/.omnix/receipts/rebuilds/"*/*.json 2>/dev/null | head -1)
if [ -z "${RECEIPT}" ]; then
    echo "ABORT: no receipt produced in .omnix/receipts/rebuilds/"
    exit 1
fi

echo "→ omnix axiom verify-rebuild $(basename "${RECEIPT}") --pubkey <project pubkey>"
omnix axiom verify-rebuild "${RECEIPT}" --pubkey "${PUBKEY}"
echo ""

REBUILT=$(ls "${SCRATCH_DIR}/.omnix/receipts/rebuilds/"*/*.java 2>/dev/null | head -1)
echo "=== rebuilt Java 21 source ==="
cat "${REBUILT}"

echo ""
echo "=== done. Receipt at ${RECEIPT} ==="
