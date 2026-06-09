# OMNIX Services

This directory contains deployable service surfaces and language adapters that
support OMNIX cloud, GitHub, and behavioral replication workflows.

## Contents

- `github-app/` - GitHub App webhook and PR surface for cloud-backed replication jobs.
- `scientist-java/` - Java Scientist adapter for dual-running legacy and candidate code.
- `scientist-node/` - Node.js Scientist adapter.
- `scientist-python/` - Python Scientist adapter.

Each service owns its local build, test, and package metadata. Keep
service-specific setup in the service README; use this file only as the index.
