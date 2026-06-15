# Governance

This document describes how OMNIX is maintained and how decisions are made. It
is intentionally lightweight, matching the project's current size and stage.

## Maintainership

OMNIX is currently maintained by a single maintainer, **Harshith Gowda**
([@gowdaharshith1998-lang](https://github.com/gowdaharshith1998-lang)), who acts
as the project lead (a "benevolent dictator" model). The maintainer is the final
decision-maker on scope, design, releases, and what is merged.

Code ownership of specific areas is recorded in
[.github/CODEOWNERS](.github/CODEOWNERS). As the project grows, additional
maintainers may be added here.

## How decisions are made

- **Discussion happens in the open** — in issues and pull requests.
- **Proposals** for non-trivial changes should start as an issue describing the
  problem and the intended approach before a large pull request is opened.
- **Disagreements** are resolved by the maintainer after weighing the
  trade-offs raised in discussion. Decisions and their rationale are recorded in
  the relevant issue or pull request.

## Releases and versioning

OMNIX follows [Semantic Versioning](https://semver.org/). The project is
pre-1.0 (currently `0.6.x`), so:

- Minor releases (`0.x.0`) may include behavior changes; breaking changes are
  called out in the [CHANGELOG](CHANGELOG.md).
- Patch releases (`0.x.y`) are fixes and small, backward-compatible additions.
- There is **no backward-compatibility guarantee before `1.0`**. Pin a version
  if you depend on current behavior.

Every user-facing change is recorded in the [CHANGELOG](CHANGELOG.md), which
follows the [Keep a Changelog](https://keepachangelog.com/) format.

## Contributing and conduct

- Contribution process: [CONTRIBUTING.md](CONTRIBUTING.md).
- Expected behavior: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
- Security policy: [SECURITY.md](SECURITY.md).
- Licensing: OMNIX is source-available; see [LICENSE](LICENSE).

## Contact

For maintainership, governance, or licensing questions, open an issue or email
**gowdaharshith1998@gmail.com**.
