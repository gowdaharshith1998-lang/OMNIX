#!/usr/bin/env bash
# Idempotent rebuild of the vendored JavaParser stack + `javaparser-emitter.jar`.
#
# Re-downloads upstream JARs, verifies SHA256 against the published Maven
# sidecars OR against the existing SHA256SUMS (whichever is present), compiles
# JavaSemanticEmitter.java against the vendored classpath, packages the runnable
# JAR with a Class-Path manifest, and runs a smoke parse on a trivial Java
# source to confirm functional integrity.
#
# Exits non-zero on any failure. Safe to re-run.
#
# Usage:
#   bash src/omnix/semantic/java/jvm/build.sh

set -euo pipefail

# ----- Pinned versions ------------------------------------------------------
# Bumping any of these is a separate single-concern slice. Update SHA256SUMS
# + test_vendor_integrity.py's _EXPECTED_JARS in lockstep.
JAVAPARSER_VERSION="3.26.3"
JAVASSIST_VERSION="3.30.2-GA"

CORE_JAR="javaparser-core-${JAVAPARSER_VERSION}.jar"
SS_JAR="javaparser-symbol-solver-core-${JAVAPARSER_VERSION}.jar"
JAVASSIST_JAR="javassist-${JAVASSIST_VERSION}.jar"
EMITTER_JAR="javaparser-emitter.jar"

MAVEN_BASE="https://repo1.maven.org/maven2"

# ----- Layout ---------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENDOR_DIR="${SCRIPT_DIR}/../vendor"
EMITTER_SRC="${SCRIPT_DIR}/JavaSemanticEmitter.java"

# ----- Pre-flight -----------------------------------------------------------
command -v javac >/dev/null || { echo "ABORT: javac not on PATH (need JDK 21+)"; exit 1; }
command -v jar   >/dev/null || { echo "ABORT: jar not on PATH"; exit 1; }
command -v java  >/dev/null || { echo "ABORT: java not on PATH"; exit 1; }
command -v curl  >/dev/null || { echo "ABORT: curl not on PATH"; exit 1; }
command -v sha256sum >/dev/null || { echo "ABORT: sha256sum not on PATH"; exit 1; }

JAVAC_VER=$(javac -version 2>&1 | awk '{print $2}' | cut -d. -f1)
if [ "${JAVAC_VER}" -lt 21 ]; then
    echo "ABORT: javac ${JAVAC_VER} too old — need JDK 21+ (JavaParser target)"
    exit 1
fi

mkdir -p "${VENDOR_DIR}"

# ----- Fetch + verify upstream JARs ----------------------------------------
# Trust model (defense in depth):
#   1. Repo-pinned SHA256SUMS is the trust root. Verified on every rebuild.
#   2. Maven Central serves .sha1 sidecars (not .sha256 for older artifacts);
#      .sha1 is checked as a transport-integrity probe — not cryptographic trust.
#   3. On initial bootstrap (no SHA256SUMS), the operator must commit the
#      regenerated file in the same review-able commit as the JAR bump.
SUMS_FILE="${VENDOR_DIR}/SHA256SUMS"

_pinned_sha256_for() {
    local jar_name="$1"
    if [ ! -f "${SUMS_FILE}" ]; then
        echo ""
        return
    fi
    awk -v name="${jar_name}" '$2 == name { print $1; exit }' "${SUMS_FILE}"
}

fetch_with_sha() {
    local jar_name="$1"
    local maven_path="$2"     # group/artifact (with slashes), e.g. "com/github/javaparser/javaparser-core"
    local version="$3"

    local target="${VENDOR_DIR}/${jar_name}"
    local url="${MAVEN_BASE}/${maven_path}/${version}/${jar_name}"

    echo "→ fetching ${jar_name}"
    local tmp
    tmp="$(mktemp -d)"
    # shellcheck disable=SC2064
    trap "rm -rf '${tmp}'" RETURN

    curl -fSL --retry 3 --max-time 60 -o "${tmp}/${jar_name}" "${url}"

    # Transport-integrity probe: Maven Central's .sha1 sidecar (always present).
    local upstream_sha1
    if upstream_sha1=$(curl -fsSL --retry 3 --max-time 15 "${url}.sha1"); then
        local actual_sha1
        actual_sha1=$(sha1sum "${tmp}/${jar_name}" | awk '{print $1}')
        if [ "${upstream_sha1}" != "${actual_sha1}" ]; then
            echo "ABORT: Maven .sha1 transport mismatch for ${jar_name}"
            echo "  upstream: ${upstream_sha1}"
            echo "  actual:   ${actual_sha1}"
            exit 1
        fi
    else
        echo "  warn: no .sha1 sidecar at ${url}.sha1 — skipping transport probe"
    fi

    # Cryptographic trust: our pinned SHA256.
    local actual_sha256
    actual_sha256=$(sha256sum "${tmp}/${jar_name}" | awk '{print $1}')

    local pinned
    pinned=$(_pinned_sha256_for "${jar_name}")
    if [ -n "${pinned}" ]; then
        if [ "${pinned}" != "${actual_sha256}" ]; then
            echo "ABORT: pinned SHA256 mismatch for ${jar_name}"
            echo "  pinned: ${pinned}"
            echo "  actual: ${actual_sha256}"
            echo "Either upstream republished the artifact (CVE / metadata fix)"
            echo "or this is a version bump — handle as a single-concern slice."
            exit 1
        fi
        echo "  ok ${actual_sha256} (matches pinned)"
    else
        echo "  ok ${actual_sha256} (bootstrap — no pinned entry; will be recorded)"
    fi

    mv "${tmp}/${jar_name}" "${target}"
}

fetch_with_sha "${CORE_JAR}" "com/github/javaparser/javaparser-core" "${JAVAPARSER_VERSION}"
fetch_with_sha "${SS_JAR}" "com/github/javaparser/javaparser-symbol-solver-core" "${JAVAPARSER_VERSION}"
fetch_with_sha "${JAVASSIST_JAR}" "org/javassist/javassist" "${JAVASSIST_VERSION}"

# ----- Compile emitter ------------------------------------------------------
echo "→ compiling JavaSemanticEmitter.java"
BUILD_DIR="${SCRIPT_DIR}/build"
rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}"

CLASSPATH="${VENDOR_DIR}/${CORE_JAR}:${VENDOR_DIR}/${SS_JAR}:${VENDOR_DIR}/${JAVASSIST_JAR}"

javac -cp "${CLASSPATH}" -d "${BUILD_DIR}" "${EMITTER_SRC}"

# ----- Package runnable JAR with Class-Path manifest -----------------------
echo "→ packaging ${EMITTER_JAR}"
MANIFEST="${BUILD_DIR}/MANIFEST.MF"
cat > "${MANIFEST}" <<MANIFEST_EOF
Manifest-Version: 1.0
Main-Class: JavaSemanticEmitter
Class-Path: ${CORE_JAR} ${SS_JAR} ${JAVASSIST_JAR}

MANIFEST_EOF

# Reproducible build: fixed timestamp so the JAR's SHA256 is deterministic
# across machines + clocks. Without this, every rebuild produces a new hash
# (ZIP entry mtimes drift), defeating the SHA256SUMS gate.
REPRODUCIBLE_EPOCH="2026-01-01T00:00:00Z"
(
    cd "${BUILD_DIR}"
    jar --create --file "${VENDOR_DIR}/${EMITTER_JAR}" \
        --manifest=MANIFEST.MF \
        --date="${REPRODUCIBLE_EPOCH}" \
        JavaSemanticEmitter.class
)

# ----- Regenerate SHA256SUMS ------------------------------------------------
echo "→ regenerating SHA256SUMS"
(
    cd "${VENDOR_DIR}"
    sha256sum "${CORE_JAR}" "${EMITTER_JAR}" "${SS_JAR}" "${JAVASSIST_JAR}" > SHA256SUMS
    sha256sum -c SHA256SUMS
)

# ----- Smoke test (self-test) ----------------------------------------------
echo "→ smoke-testing emitter on trivial Java source"
SELFTEST_DIR="$(mktemp -d)"
trap 'rm -rf "${SELFTEST_DIR}"' EXIT
cat > "${SELFTEST_DIR}/Trivial.java" <<'JAVA_EOF'
public class Trivial {
    public String greet(String name) {
        return "Hello, " + name;
    }
}
JAVA_EOF

SELFTEST_OUT="$(java -jar "${VENDOR_DIR}/${EMITTER_JAR}" "${SELFTEST_DIR}/Trivial.java")"

if ! echo "${SELFTEST_OUT}" | grep -q '"fqn":"Trivial.greet"'; then
    echo "ABORT: smoke test failed — emitter did not produce expected node"
    echo "stdout was:"
    echo "${SELFTEST_OUT}"
    exit 1
fi
if ! echo "${SELFTEST_OUT}" | grep -q '"resolved_return_type":"java.lang.String"'; then
    echo "ABORT: smoke test failed — return type not resolved to java.lang.String"
    echo "stdout was:"
    echo "${SELFTEST_OUT}"
    exit 1
fi

# ----- Clean build dir ------------------------------------------------------
rm -rf "${BUILD_DIR}"

echo ""
echo "OK: emitter functional"
JAR_BYTES=$(stat -c '%s' "${VENDOR_DIR}"/*.jar 2>/dev/null | awk '{sum+=$1} END {printf "%.1f MB", sum/1024/1024}')
echo "    vendored: $(ls -1 "${VENDOR_DIR}"/*.jar | wc -l) JARs (${JAR_BYTES})"
echo "    artifact: ${VENDOR_DIR}/${EMITTER_JAR}"
