#!/usr/bin/env bash
# Build an OMNIX airgap bundle.
#
# Output: omnix-airgap-<version>.airgap (single tarball containing:
#   - docker image archives for api / studio / verifier
#   - helm chart
#   - KOTS manifests
#   - README + verification instructions
#
# Usage:
#   ./deploy/build-airgap.sh [VERSION] [PLATFORM]
set -euo pipefail

VERSION="${1:-$(cat VERSION 2>/dev/null || echo dev)}"
PLATFORM="${2:-linux/amd64}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

echo "==> Building OMNIX airgap bundle ${VERSION} for ${PLATFORM}"
mkdir -p "${WORK}/images" "${WORK}/helm" "${WORK}/kots"

build_and_save() {
    local name="$1" dockerfile="$2"
    echo "==> building image ${name}:${VERSION}"
    docker build --platform "${PLATFORM}" -t "ghcr.io/gowdaharshith1998-lang/${name}:${VERSION}" \
        -f "${dockerfile}" "${ROOT}"
    docker save "ghcr.io/gowdaharshith1998-lang/${name}:${VERSION}" \
        > "${WORK}/images/${name}.tar"
}

build_and_save "omnix-cloud-api"  "${ROOT}/deploy/docker/api.Dockerfile"

# Studio + verifier reuse the api image but ship as separate logical images so
# that operators can scale them independently. The chart command flags select
# the entry point.
cp "${WORK}/images/omnix-cloud-api.tar" "${WORK}/images/omnix-studio.tar"
cp "${WORK}/images/omnix-cloud-api.tar" "${WORK}/images/omnix-verifier.tar"

echo "==> packaging helm chart"
helm package "${ROOT}/deploy/helm/omnix" -d "${WORK}/helm" --version "${VERSION}" --app-version "${VERSION}"

echo "==> bundling KOTS manifests"
cp -r "${ROOT}/deploy/kots/." "${WORK}/kots/"

cat > "${WORK}/README.md" <<EOF
OMNIX Airgap Bundle — ${VERSION}

Contents:
  images/      docker image archives (load with: docker load -i <file>)
  helm/        helm chart (install with: helm install omnix ./helm/omnix-${VERSION}.tgz)
  kots/        Replicated KOTS manifests for kots install

Verify bundle:
  sha256sum -c omnix-airgap-${VERSION}.airgap.sha256
  verify omnix-airgap-${VERSION}.airgap.sig with the release public key before loading images
EOF

out="${ROOT}/dist/omnix-airgap-${VERSION}.airgap"
mkdir -p "${ROOT}/dist"
tar -C "${WORK}" -czf "${out}" .
echo "==> wrote ${out} ($(du -h "${out}" | awk '{print $1}'))"
sha256sum "${out}" > "${out}.sha256"
echo "==> sha256 ${out}.sha256"
