# Release v2.23.0

## Highlights

- Added a real SolidWorks Toolbox model-library E2E command: `cad_pipeline.py sw-toolbox-e2e`.
- Added manual GitHub `sw-smoke full=true` validation for self-hosted Windows runners.
- Verified Toolbox SLDPRT → STEP export and generated `std_*.py` STEP consumption through the production resolver/codegen path.

## Reliability Fixes

- Bearing model config matching now recognizes controlled 4/5 digit bearing tokens such as `6205`.
- `PartsResolver` propagates `NeedsUserDecision` instead of treating it as a generic adapter crash.
- SW config workers handle both `ModelDoc2.GetConfigurationNames()` and `ConfigurationManager.GetConfigurationNames()` paths.
- The Toolbox E2E fixture refreshes `cad_paths.PROJECT_ROOT` after setting `CAD_PROJECT_ROOT`, preventing decisions/pending files from drifting to the repo root.

## Validation

- Local: `1546 passed, 16 skipped, 2 deselected`, coverage gate `95.56%`.
- GitHub PR CI: all Ubuntu/Windows Python matrix jobs, regression, and mypy-strict passed.
- Self-hosted Windows full smoke: `sw-smoke full=true` run `25064438363` passed.

PyPI upload intentionally skipped for this release.
