# Release v2.23.5

Model-library release for user-supplied STEP assets, model audit, and broader demo subsystem coverage.

## Added

- Added `cad_pipeline.py model-audit` / `tools/model_audit.py` for read-only geometry quality reporting without mutating model-library state.
- Added `tools/model_import.py` and structured model-choice persistence so user-provided STEP files are copied into `std_parts/user_provided/` and routed through `parts_library.yaml`.
- Added FreeCAD-library attribution and three user-provided STEP examples for lifting-platform coverage.
- Expanded end-effector shared-cache vendor synthesizers and default mappings so all 32 generated purchased parts route to STEP imports.

## Changed

- Upgraded lifting-platform standard part scaffolds from simplified geometry to user-provided / real STEP imports where available.
- Upgraded end-effector standard part scaffolds to import synthesized shared-cache STEP files instead of reverting to JINJA fallback geometry.
- Exposed `DEFAULT_STEP_FILES` in `adapters.parts.vendor_synthesizer` so YAML mappings and batch cache warmup share one path contract.

## Fixed

- Fixed model-choice path anchoring so user-provided STEP paths stay rooted in the project instead of drifting across working directories.
- Unified shared-cache STEP path resolution between resolver reports, generated code, and cache validation.
- Narrowed GISBOT-specific end-effector default mappings to exact `GIS-EE-*` part numbers so generic parts named like "齿轮泵" or "阻尼垫" do not resolve to demo-specific stand-ins.
- Added Python 3.10 compatibility coverage for f-string syntax used in generated/reporting code paths.

## Validation

- Local full suite after merging to `main`: `1697 passed, 16 skipped, 4 warnings`.
- PR #43 checks: mypy-strict, regression, Ubuntu/Windows Python 3.10/3.11/3.12 all passed.
- Post-merge `main` checks: tests matrix and `sw-smoke` passed.
- `end_effector` model audit: `A=32`, `missing_step_count=0`, `review_required_count=0`.

PyPI upload intentionally skipped for this release.
