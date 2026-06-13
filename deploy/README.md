# OMNIX Deployment

Deployment assets for OMNIX enterprise and air-gapped installations.

## Contents

- `docker/` - container build files and Studio nginx config.
- `helm/omnix/` - primary Helm chart for Kubernetes installs.
- `kots/` - Replicated KOTS app, config, and preflight manifests.
- `build-airgap.sh` - builds an offline bundle with images, Helm chart, and KOTS manifests.

See `docs/deploy/airgap.md` for the operator-facing air-gapped install guide.
