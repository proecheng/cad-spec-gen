# Release v2.23.3

Patch release for end-effector model quality and test import determinism.

## Changed

- Upgraded the remaining five D-grade `JINJA_PRIMITIVE` end-effector purchased/fallback parts to C-grade semi-parametric `JINJA_TEMPLATE` models:
  - `GIS-EE-001-04` Belleville spring washer
  - `GIS-EE-003-05` viscoelastic damping pad
  - `GIS-EE-003-07` tungsten counterweight slug
  - `GIS-EE-004-05` elastomer cushion pad
  - `GIS-EE-004-10` tungsten counterweight slug
- Preserved the `GIS-EE-003-05` 20mm AE serial-chain axial envelope so the quality upgrade does not move the assembly stack.
- Raised the end-effector geometry report from `A=9, C=18, D=5` to `A=9, C=23, D=0`.

## Fixed

- Track-C tests now prefer the repository `src/` package over any locally installed older `cad-spec-gen` package, avoiding import-path drift in developer environments.

## Validation

- Local full test suite: `1619 passed, 16 skipped`
- Local targeted tests: `172 passed, 2 skipped`
- Local end-effector build: `cad_pipeline.py build --subsystem end_effector`
- Assembly report: `0 WARNING`, F5 `33/33`
- PR #31 and PR #32 CI: Ubuntu/Windows Python 3.10/3.11/3.12, regression, and mypy-strict all passed.

PyPI upload intentionally skipped for this release.
