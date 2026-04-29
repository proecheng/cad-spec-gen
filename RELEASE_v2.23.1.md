# Release v2.23.1

Patch release for model-library routing and sample geometry quality.

## Fixed

- `StepPoolAdapter` supports safe `file_template` lookup such as `{normalize(name)}.step`, keeps explicit `file` mappings first, and rejects `../` path escape.
- Generated sample scaffolds under `cad/` no longer contain bare `TODO:` placeholders; a regression test guards this.
- Explicit connection-matrix axial gaps now render into `CAD_SPEC.md` §4 and feed serial assembly stacking.
- Part-number matching now uses separated identifier matching, so numeric IDs like `100` do not leak into `1000`.
- Negative or invalid axial gaps are normalized to `0.0`.

## Validation

- Local targeted tests: `33 passed`
- Local downstream walker/BOM tests: `106 passed`
- PR #25 CI: Ubuntu/Windows Python 3.10/3.11/3.12, regression, and mypy-strict all passed.
