# Internal Documentation Map

These files are engineering history and planning material. They are useful for
maintainers, but they are not the canonical public product description.

## Current Public Sources

- `README.md` - product overview, quickstart, roadmap, and status matrix.
- `docs/README.md` - documentation entry point.
- `docs/dm/README.md` - OMNIX-DM status, phase map, and explicit gaps.
- `services/README.md` - service/package map.
- `deploy/README.md` - deployment surfaces.
- `SECURITY.md` - vulnerability reporting and security posture.
- `CONTRIBUTING.md` - local development and pull request expectations.

## Internal And Historical Sources

- `NOTES.md` - engineering log of shipped slices and follow-up context.
- `TODOS.md` - active backlog and known blockers.
- `AUDIT.md` - audit/verification notes.
- `DESIGN.md` - visual/brand design reference (color, type, layout language); NOT software architecture.
- `CHANGELOG.md` - chronological changes.
- `slices/` - historical slice plans.
- `docs/XFAIL_AUDIT.md` - expected-failure marker ownership.
- `tests/_blocked/**` - blocked test rationale, kept out of default test runs.
- `src/omnix/studio/NOTES.md` - Studio-specific implementation notes.

## Maintenance Rules

- Keep public claims in `README.md`, `docs/dm/README.md`, and service/deploy
  READMEs aligned with verified behavior.
- Keep historical planning terms in internal files unless they are still part
  of the current user-facing product surface.
- When a blocked test becomes active, update the matching rationale file or
  remove it in the same change.
