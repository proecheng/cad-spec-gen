# Release v2.24.0

Model-library invocation loop release for stable model paths, read-only SolidWorks planning, and hash-bound user STEP imports.

## Added

- Added `ModelProjectContext` as the stable path contract for model choices, standard-part directories, reports, and subsystem outputs.
- Added read-only `cad_pipeline.py sw-export-plan` / `tools/sw_export_plan.py` so review and planning can inspect candidate SolidWorks exports without triggering COM export side effects.

## Changed

- `parts_library.yaml` updates are now atomic, preserve `extends: default`, and prepend new user-provided mappings so the next codegen run consumes the selected model.
- Generated standard-part modules now record geometry source, A-E quality, validation state, STEP hash, path kind, and manual-review flags in their docstrings.
- SolidWorks Toolbox planning reports explicit `export` or `reuse_cache` actions and treats missing config names as `Default`.

## Fixed

- User STEP imports now validate CadQuery bounding boxes and source hashes before copying into managed `std_parts/user_provided/` paths.
- Managed user STEP filenames include a 12-character source hash suffix, preventing same-name model files with different geometry from overwriting each other.
- Legacy shared-cache bare STEP filenames remain discoverable by the export planner.

## Validation

- Local full suite: `1738 passed, 16 skipped, 4 warnings`.
- Local focused model-library suite: `170 passed`.
- `scripts/dev_sync.py --check` and `git diff --check` passed.
- `end_effector` model audit: `A=32`, `missing_step_count=0`, `review_required_count=0`.
- PR #44 checks: mypy-strict, regression, Ubuntu/Windows Python 3.10/3.11/3.12 all passed.

PyPI upload intentionally skipped for this release.
