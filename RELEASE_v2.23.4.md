# Release v2.23.4

Patch release for CI/runtime stability.

## Changed

- Upgraded `actions/upload-artifact` from v4 to v7 in both CI workflows:
  - `.github/workflows/tests.yml`
  - `.github/workflows/sw-smoke.yml`
- This moves artifact upload steps from the deprecated Node 20 action runtime to Node 24.

## Added

- Added a workflow contract test to prevent `actions/upload-artifact@v4` from returning to CI.

## Validation

- Local targeted tests: `15 passed`
- Local full test suite: `1648 passed, 16 skipped`

PyPI upload intentionally skipped for this release.
