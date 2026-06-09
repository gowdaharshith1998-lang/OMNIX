# Contributing to OMNIX

OMNIX is source-visible commercial software. Contributions, issues, and pull
requests are welcome for evaluation and collaboration, but this repository is
not distributed under an open-source license. See `LICENSE.md` before reusing
code outside evaluation.

## Development

- Python install: `pip install -e ".[dev]"`
- Python tests: `pytest tests/ -q --tb=line`
- Python lint: `ruff check .`
- Python types: `mypy src/omnix --ignore-missing-imports`
- Vault tests: `npm test`
- GitHub App: run build and tests from `services/github-app/`

## Pull Requests

Keep changes focused, include tests for behavior changes, and call out
security-sensitive paths. Do not include secrets, customer code, generated
credentials, or proprietary third-party artifacts.
