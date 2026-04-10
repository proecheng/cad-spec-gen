# Spec 2 — Asset Library, PBR Textures, Auto-Routing, Review E Dimension

**Date**: 2026-04-10 (original) / restructured after multi-perspective review
**Status**: ⏸️ **DEFERRED** — design skeleton only, NOT ready for implementation
**Prerequisite**: [Spec 1 — Foundation](./2026-04-10-spec1-foundation-design.md) must ship first
**Scope**: The full three-tier asset library, network-facing features, review E dimension, and everything the two rounds of review surfaced as "needs more work before ship"

---

## 0. Status — Why This Spec Is Deferred

The original version of this document tried to ship everything in one go: FOV fix + templates + PBR textures + auto-routing + CLI + Phase R review enhancement, all unified under a three-tier asset library.

Two rounds of multi-perspective review (8 reviewers total — system architect, skill-writing expert, end user, 3D designer, security engineer, QA test architect, DevOps/release engineer, Chinese engineering workflow expert) surfaced **50+ distinct issues**. The most damning was the **security review rating of 2/10**, driven by the plugin-system / arbitrary-code-execution / auto-download / unsigned-manifest combination.

**Decision**: split into two specs. [Spec 1](./2026-04-10-spec1-foundation-design.md) ships the foundation (FOV fix, 5 templates, `parts_routing.py` module, packaging fix, local-only `cad-lib` CLI, schema versioning) — zero network, zero arbitrary code execution, zero breaking visual changes. This Spec 2 captures everything else as a deferred skeleton.

**This document is not ready for implementation**. Before it becomes implementation-ready, the following work must be completed and incorporated:

1. **§16 Security Model** — full threat model, manifest signing design, safe-zip-extraction spec, URL allowlist, path validation regex, `importlib` avoidance strategy
2. **§17 Chinese Keyword Expansion** — 3× expansion of the keyword table to ~40 entries, traditional-character normalization layer, regex with `形/型` infix support, GB material alias table, GB/T fastener standard equivalences
3. **§18 PBR Physics Corrections** — replace Generated-coords with box projection at constant texel density, real tangent field strategy for anisotropic materials, Coat layer + thin-film IOR for anodizing, engineering vs marketing lighting modes, per-material hash-seeded variation
4. **§19 Release Engineering** — feature flag wiring, v3.0 migration guide, CHANGELOG template, post-install banner, rollback story, multi-version coexistence
5. **§20 AI Enhancement × PBR Conflict Resolution** — per-material AI enhance toggle, ControlNet hint pass, multi-view consistency plan

None of the above can be hand-waved. Each section needs real design work before code can ship.

---

## 1. Relationship to Spec 1

Spec 2 depends on Spec 1 having shipped. Specifically, Spec 2 consumes:

| From Spec 1 | Used by Spec 2 | Why |
|------------|---------------|-----|
| `src/cad_spec_gen/data/python_tools/render_3d.py` (canonical) | Phase 3 PBR texture loading | FOV fix must already exist; PBR hooks into `create_pbr_material()` |
| `src/cad_spec_gen/data/python_tools/parts_routing.py` (pure module) | Phase 4 auto-routing + Phase R review dimension E | Single source of truth for matching decisions; prevents aspirational "E and resolver share simulation path" invariant from being hand-waved |
| 5 base templates + `MATCH_KEYWORDS` contract | Phase 4 auto-routing routes TO them; Phase R checks for coverage | — |
| `cad-lib` local CLI (init/doctor/list/which/validate) | Extended with install/add/import/report/sync/create/import | Spec 2 builds on the verb surface, doesn't replace it |
| Schema versioning foundation | All new YAMLs in Spec 2 inherit `schema_version: 1` discipline | Migration story |
| Feature flag env vars reserved in Spec 1 | Each Spec 2 phase ships behind its reserved flag, default OFF | Rollback / phased rollout |
| Fixed packaging in `hatch_build.py` | New Spec 2 files (manifest, cad_lib extensions, `cad_spec_reviewer.py` updates) piggyback on the fixed pipeline | — |
| Test isolation infrastructure (`tests/conftest.py` autouse fixture) | All Spec 2 tests inherit the home-dir tripwire | Prevents real home pollution |

## 2. Goals (Deferred from Original Spec)

- **G3 — Enable PBR texture maps with graceful scalar fallback** (Phase 3)
- **G4 — Auto-route BOM items to templates when keywords match** (Phase 4, building on Spec 1's `parts_routing.py`)
- **G5 — Architectural: three-tier asset library** (built-in → user shared → project local) that is downloadable on demand and grows with user activity
- **G8 — Shift-left asset library readiness via the review step** — extend `cad_spec_reviewer.py` with dimension E (资产库就绪度审查). **Reframed**: not a "precheck that blocks" but an "advisory engine with opt-in `--strict` mode for CI gates." The original G8 framing conflicted with the non-blocking invariant; see §3 for the reframe.
- **G12 — Secure supply chain** (NEW, from security review): every downloadable asset is signed, verified before write, and loaded through mechanisms that do not trigger arbitrary code execution
- **G13 — Real Chinese engineering support** (NEW, from Chinese engineering review): keyword table covers ~40 common nouns, handles traditional characters, handles full-width digits, maps GB material aliases, maps GB/T fastener standards to ISO equivalents
- **G14 — Physically plausible PBR** (NEW, from 3D designer review): texture mapping produces constant texel density regardless of part size, anisotropic materials have real tangent fields, anodizing uses a coat-layer physics model
- **G15 — Shippable release** (NEW, from DevOps review): feature flags for phased rollout, v3.0 migration guide, CHANGELOG artifact, rollback path, schema forward/backward compat

## 3. Architectural Reframe — G8 "Shift-Left" Correction

The original G8 said "catches asset library gaps BEFORE codegen runs — so every downstream phase enters execution with a known-good asset posture." Invariant #8 simultaneously said "E never blocks; only WARNING/INFO." The architect review called this a contradiction — a review that cannot block is not a precheck.

**Correct framing** (to be used throughout Spec 2):

> **G8 (revised)**: The review dimension E (`资产库就绪度`) is an **advisory engine** that surfaces asset library gaps during the spec review step. It makes the gaps visible, documents concrete remediation commands, and feeds a `suggestions.yaml` log that drives library growth. It is **non-blocking by default** because the pipeline must always be runnable offline with Jinja2 + scalar fallback.
>
> For CI usage where "green build requires zero library gaps" is desired, E ships with a `--strict` opt-in flag (default off) that promotes all E warnings to errors. Teams running `cad-spec --review --strict` can gate PRs on asset library completeness without forcing the default path to be blocking.

This reframe is NOT a feature change — it's an honest description of what the review actually does. It also neutralizes the architect's objection and resolves the "wall of yellow that everyone ignores" concern from the skill-writing review.

## 4. Deferred Feature Catalog

### 4.1 Three-Tier Asset Library (Full)

Tier 2 (`~/.cad-spec-gen/`) gains the full asset types:
- `~/.cad-spec-gen/shared/templates/` — user + community downloaded templates
- `~/.cad-spec-gen/shared/textures/` — PBR texture packs
- `~/.cad-spec-gen/shared/models/` — parametric model families (NEMA motors, etc.)
- `~/.cad-spec-gen/shared/materials.yaml` — user material preset extensions
- `~/.cad-spec-gen/shared/library.yaml` — user routing rules + keyword overrides
- `~/.cad-spec-gen/state/installed.yaml` — auto-maintained install log (with `schema_version: 1` from Spec 1)
- `~/.cad-spec-gen/state/suggestions.yaml` — fallback log

**Key constraint from security review**: `~/.cad-spec-gen/shared/templates/` cannot be loaded via `importlib.import_module()` without the security model's gate (see §16). The current Spec 1 `parts_routing.py` only reads descriptors via AST parsing; Spec 2 extends this but any actual `make()` execution of a Tier 2 template must pass through the trust workflow.

### 4.2 Library Manifest (`catalogs/library_manifest.yaml`)

Ships with skill. Lists available downloadable assets with metadata (source, URL, license, checksum, keyword bindings). **Must be signed** (see §16).

Initial seed covers 7 texture packs (ambientCG CC0), 4 builtin templates (for discoverability by the user library), 0 models. Structure per the original spec §4.3 but with added `signature` and `manifest_signature` fields.

### 4.3 PBR Texture System (Phase 3, rewritten per 3D designer review)

- **Auto-upgrade pattern**: scalar fallback always works; textures layer on top if present
- **Box projection, not Generated coords** (3D designer #1): use `ShaderNodeTexImage.projection='BOX'` with `projection_blend ≈ 0.3`, World-space Object coords, Mapping node scale driven by `1 / target_texel_size_m` for constant texel density
- **Real tangent field** (3D designer #2): `ShaderNodeTangent.Radial` for turned parts, `Smart UV Project` bake for milled parts — classified by template category or explicit per-material hint
- **Anodizing physics** (3D designer #3): Principled Coat layer + thin-film IOR, NOT `MixRGB(Multiply)`. Roughness +0.05 over bare aluminum, Fresnel-driven grazing desaturation.
- **Per-material hash-seeded variation** (3D designer #6): Object Info → Random → Mapping offset so repeated exposure to the same texture pack doesn't asset-flip
- **Lighting modes** (3D designer #5): `render_config.lighting_mode: "engineering" | "marketing"`. Engineering = HDRI + soft key only (neutral, no rim). Marketing = current 4-light rig but with rim gated to <40% key intensity.
- **Expanded material seed** (3D designer missing-categories): add powder coat, raw ABS, machined titanium, electropolished stainless, black oxide steel — can't represent any non-metallic or coated finish with the current 7-pack seed

### 4.4 Full Template Auto-Routing (Phase 4)

Uses Spec 1's `parts_routing.py` module. Adds:
- `parts_library.default.yaml:template_routing` section with YAML rules
- `_bridge_params(template, geom_info)` in `gen_parts.py` for parameter mapping
- Template `ParamSchema` TypedDict (architect #3) — replaces the dict-based interface with typed schemas; CI lint validates schema ↔ signature ↔ `example_params` coherence
- Emitted code uses `from templates.parts import <name>` when matched; falls back to Jinja2 when not
- Feature flag `CAD_SPEC_GEN_TEMPLATE_ROUTING=1` required to enable; OFF by default in v3.0.0, ON by default in v3.1.0 after one release of validation

### 4.5 `cad-lib` Extended Verbs

Extends Spec 1's local CLI with network + code-moving commands, **all gated behind security review §16**:

- `cad-lib add {texture|template|material|model} <name> [--from|--file|--preset]` — unified verb surface (skill-writing expert #2); replaces original inconsistent `install texture` / `add-material` / `create template` / `import template`
- `cad-lib remove <kind> <name>` — uninstall + update `installed.yaml`
- `cad-lib sync` — refresh manifest from remote (signature verified)
- `cad-lib apply-review <DESIGN_REVIEW.json>` — interactively execute structured actions emitted by Phase R (replaces brittle copy-paste from §9.5.3 of the original)
- `cad-lib trust <name>` — mark a Tier 2 template as trusted for execution (security gate, see §16)
- `cad-lib audit` — list Tier 2 templates with sha256 + git provenance; warn on untrusted

### 4.6 Phase R — Review Dimension E (Revised)

The original §9.5 is mostly retained, with these corrections:

1. **Reframed as advisory, not precheck** (per §3 above, G8 correction)
2. **`--strict` mode** added for CI gating
3. **E1 and E2 ship together in Phase 4**, not split across P2/P4 — the split was a source of the "aspirational invariant #9" drift
4. **All E checks call `parts_routing.route()`** from Spec 1, not duplicate logic
5. **Machine-readable output** — `DESIGN_REVIEW.json` gains an `actions: [{tool, args, kind}]` field for agent consumption (skill-writing expert #1)
6. **Determinism splits** — E output sections are tagged `deterministic` (spec-intrinsic: E1 routing, E3 preset name match, E5 keyword consistency) or `local-environment` (E4 texture install status, which depends on local state). CI diff-checking only validates deterministic sections. (architect #6)
7. **Summary-first output** (end user #3) — per-part details collapsed behind `--verbose`; default output shows counts + suggestions only

### 4.7 AI Agent Integration

New (skill-writing expert #1): ship a `cad-lib` SKILL.md with triggers ("textures missing", "template fallback", "asset library", "add material preset") so Claude Code and similar agents can invoke the library operations without human-in-the-loop. The SKILL.md consumes the machine-readable `actions` field from §4.6.

### 4.8 Team Sharing Story

Per end-user review #6: `~/.cad-spec-gen/` split into `shared/` (git-safe) and `state/` (machine-local) is established in Spec 1 already. Spec 2 adds:
- A sample README in `shared/` explaining "this directory is safe to git-sync"
- `cad-lib init --team-lead` variant that writes a starter `library.yaml` with team defaults
- Documentation in the migration guide (§19) explaining the team workflow

### 4.9 Migration Extensions

Spec 1 ships `cad-lib migrate-subsystem` for FOV fix propagation. Spec 2 extends:
- `cad-lib migrate frame-fill` — rewrites `render_config.json` to explicit values for users who don't want the new formula
- `cad-lib migrate template-routing` — updates `parts_library.yaml` with default routing rules when upgrading from pre-Spec-2
- `cad-lib doctor --verbose` — enhanced diagnostic for v3.0 → v3.1 transitions

## 5. Full Reviewer Findings Index

This section catalogs every finding from the 2 review rounds (8 reviewers) that this spec must address before implementation. Each item has an owner phase and a status.

### 5.1 Round 1 Findings (pre-split; items in this list that Spec 1 already handles are marked ✅)

| # | Reviewer | Finding | Status |
|---|----------|---------|--------|
| A | Architect | Shift-left vs non-blocking paradox | Addressed by G8 reframe (§3) |
| B | Architect + User | `render_3d.py` file architecture (4 versions) | ✅ Spec 1 §5.4 |
| C | Architect | Invariant #9 aspirational (parts_routing not extracted) | ✅ Spec 1 §7 |
| D | User + 3D Designer | Templates end-effector biased | Partially addressed (Spec 1 adds `fixture_plate`; Spec 2 adds more categories) |
| E | Skill Expert + User | Tier 2 seven-file mental overload | ✅ Spec 1 §8.2 (split shared/state); Spec 2 consolidates library.yaml subsections |
| F | Architect | `_bridge_params` leaky dict interface | Spec 2 §4.4 — `ParamSchema` TypedDict |
| G | Architect | No Tier 2 schema versioning | ✅ Spec 1 §10 foundation |
| H | Architect | E output determinism vs three-tier | Spec 2 §4.6 — split deterministic/local |
| I | Skill Expert | No AI agent entry point | Spec 2 §4.7 — `cad-lib` SKILL.md |
| J | Skill Expert | `cad-lib` verb inconsistency | Spec 2 §4.5 — unified `add` verb |
| K | Skill Expert | No `which`/`doctor`/`init` | ✅ Spec 1 §8.1 |
| L | Skill Expert | Copy-paste suggestions brittle | Spec 2 §4.6 — machine-readable actions |
| M | User | 50 parts → E output wall | Spec 2 §4.6 — summary-first |
| N | User | Offline handling ambiguous | Spec 2 §19 — `--offline` flag + render metadata |
| O | User | Git-sharing + machine state conflict | ✅ Spec 1 §8.2 (shared/state split); Spec 2 §4.8 — documentation |
| P | User | No walked template example | Spec 2 §17 companion — quickstart guide |
| Q, R, S, T, U, V, W, X | 3D Designer | PBR physics corrections (all 8) | Spec 2 §18 |

### 5.2 Round 2 Findings (post-first-review; drove the split to strategy D)

| # | Reviewer | Finding | Status |
|---|----------|---------|--------|
| Y | Security | 7 security issues rated 2/10 | **Spec 2 §16 — BLOCKING until drafted** |
| Z | DevOps | Wheel packaging gap | ✅ Spec 1 §9 |
| AA | Chinese Eng | Keyword table is toy-level | Spec 2 §17 — BLOCKING until expanded |
| BB | Chinese Eng | No traditional character handling | Spec 2 §17 |
| CC | Chinese Eng | Material alias explosion | Spec 2 §17 |
| DD | Chinese Eng | No GB standards integration | Spec 2 §17 |
| EE | QA | Determinism flakes on Windows | ✅ Spec 1 §13.1 (PYTHONHASHSEED, newline="\n") |
| FF | QA | `~/.cad-spec-gen/` pollution risk | ✅ Spec 1 §13.1 (autouse tripwire fixture) |
| GG | DevOps | No feature flags | ✅ Spec 1 §8.4 (env vars reserved); Spec 2 uses them |
| HH | DevOps | SemVer break on frame_fill | ✅ Spec 1 §5.3 (keep 0.75, no break) — Spec 2 needs full migration guide |
| II | QA | pytest-xdist + dynamic discovery deadlock | Spec 2 §18 testing addendum |
| JJ | QA | Blender golden image protocol | ✅ Spec 1 §13.2 (silhouette comparison, version pin) |

### 5.3 Summary

**Blocking items for Spec 2 implementation** (must be drafted into design before any code):

1. **§16 Security Model** (Round 2, Y) — the entire security posture
2. **§17 Chinese Keyword Expansion** (Round 2, AA+BB+CC+DD) — 3× expansion with GB + traditional + materials
3. **§18 PBR Physics Corrections** (Round 1, Q+R+S+T+U+V+W+X) — all 8 designer findings
4. **§19 Release Engineering** (Round 2, HH + GG + Z) — feature flags, migration guide, release communication

Each of these is effectively its own sub-spec that needs real design work before Spec 2 is implementation-ready.

## 6. Sections to Be Drafted

### §16 Security Model — BLOCKING

Must cover:
- Threat model (adversaries, assets, trust roots)
- Manifest signing: key management (where are maintainer keys stored, rotation, revocation), signing tool (`minisign` or `sigstore`), verification on every load
- Checksum-before-write: download to temp, verify, then move to destination; never write-then-verify
- Safe zip extraction: path normalization, zip bomb check (max uncompressed size 100MB), extension allowlist (`.jpg`, `.png`, `.yaml`)
- URL allowlist: `https://` only; host in `{ambientcg.com, raw.githubusercontent.com/<trusted-org>}`
- Template validation via AST parse only — never `importlib` during validation
- Template execution requires `cad-lib trust <name>` sign-off
- `cad-lib audit` command design
- Path validation regex `^[a-z0-9_]{1,64}$` for every `<name>` CLI arg
- `CAD_SPEC_GEN_AUTO_DOWNLOAD=1` restricted to textures only (inert data); template/model downloads require interactive confirmation even with flag
- Negative security test suite (zip bomb, ZipSlip, bad signature, bad checksum, scheme rejection, path traversal)
- Audit trail: every `cad-lib install` logs to `installed.yaml` with source URL, sha256, timestamp
- Offline mode: `CAD_SPEC_GEN_OFFLINE=1` disables all network; grep-enforced in CI
- ambientCG mirror / availability fallback story
- Cloned `~/.cad-spec-gen/` trust model: cloned libraries are untrusted until audited

### §17 Chinese Keyword Expansion — BLOCKING

Must cover:
- Expanded keyword table (~40 entries minimum) grouped by morphology family
- Traditional character normalization layer (opencc or hand-maintained S↔T dict for the ~40 keywords)
- NFKC width normalization for full-width digit support (`unicodedata.normalize('NFKC', material)`)
- Regex matchers with optional `形/型/式/状` infix (e.g., `L[形型]?\s*(支架|架|角码)`)
- Negative keyword column (e.g., `套管` disqualifies cylindrical_housing; `散热/翅片` disqualifies plain box housing)
- Material alias file `materials_aliases.yaml` covering:
  - Carbon steel variants (`45#钢`, `45号钢`, `45钢`, `优质碳钢45`)
  - Structural steel (`Q235`, `Q235B`, `Q235-A`, `A3钢`)
  - Stainless (`304`, `SUS304`, `06Cr19Ni10`, `0Cr18Ni9`, `1Cr18Ni9Ti`, `022Cr17Ni12Mo2`)
  - Aluminum (`6061-T6`, `6061T6`, `LY12`, `2A12`)
- GB/T ↔ ISO fastener equivalence file `gb_iso_equivalence.yaml`:
  - GB/T 70.1 ≈ ISO 4762 (socket head cap screws)
  - GB/T 5783 ≈ ISO 4017 (hex head bolts)
  - GB/T 97.1 ≈ ISO 7089 (flat washers)
  - GB/T 276 = ISO 15 (deep groove ball bearings)
  - ~30 most-cited standards minimum
- Envelope notation parser extensions:
  - `φ`, `Ø`, `∅`, `直径N` diameter variants
  - `长×宽×高`, `L×W×H` dimension labels
  - Range notation `Φa-Φb×L` for stepped shafts
  - Full-width digit handling via NFKC
- Validation corpus: 500+ real BOM entries from Chinese manufacturing (source: anonymized partner data; must be collected before implementation)

### §18 PBR Physics Corrections — BLOCKING

Must cover:
- Replace `ShaderNodeTexCoord.Generated` with Box Projection at constant texel density
- Texel density calculation: `Mapping.Scale = 1 / target_texel_size_m` where target varies by material category (aluminum ~15cm, plastic ~10cm)
- Turned vs milled classification for tangent strategy:
  - Turned parts (cylindrical_housing, iso_9409_flange): `ShaderNodeTangent.Radial`
  - Milled parts (l_bracket, rectangular_housing, fixture_plate): Smart UV Project bake at build time
  - Classification via `TEMPLATE_CATEGORY` or explicit per-material override
- Anodizing shader graph:
  - Base: Principled BSDF with brushed aluminum base + tint multiply
  - Coat: Principled Coat layer, Weight=0.3, Roughness=0.1-0.15, IOR=1.5
  - Roughness delta: +0.05 over bare aluminum
  - Grazing desaturation: Fresnel → MixRGB(Mix) between saturated and desaturated tint
- Per-material variation: Object Info → Random → Vector Math to offset Mapping Translation/Rotation per object
- Expanded material seed (not just metals):
  - `powder_coat_matte_black` — semi-matte, subtle orange-peel normal
  - `painted_mild_steel` — thicker clearcoat than anodizing
  - `raw_abs_plastic` — micro-flow lines + sprue marks (procedural noise)
  - `machined_titanium` (Ti-6Al-4V) — characteristic blue-gray, lower reflectance than stainless
  - `black_oxide_steel` — very dark, low saturation, slight blue tint
  - `electropolished_stainless` — mirror-adjacent, roughness 0.08
- Two lighting modes in `render_config.json`:
  - `engineering` — HDRI-only (royal_esplanade_1k or studio_small_08) at 1.2 strength + single soft key at 45°; no rim
  - `marketing` — current 4-light rig with rim gated to <40% of key
- Cycles settings: `glossy_bounces=4` (down from 8) for opaque metal — reallocate budget to samples

### §19 Release Engineering — BLOCKING

Must cover:
- Semver decision: v3.0.0 MAJOR (because of architectural changes introduced + breaking `parts_library.yaml` schema for auto-routing). v2.9.0 is Spec 1 MINOR (compatible, additive only).
- Feature flag defaults and rollout phases:
  - v3.0.0: all Spec 2 flags OFF by default (dark ship)
  - v3.0.1: enable safe flags (PBR textures, Phase R in advisory mode)
  - v3.1.0: enable auto-routing after a release of validation
- Migration guide `docs/migration/v2.8-to-v3.0.md`:
  - `frame_fill` behavior change narrative (preserving 0.75 default helps, but still needs explanation)
  - `parts_library.yaml` template_routing section addition
  - `~/.cad-spec-gen/` directory creation on first run
  - Phase R warnings explanation
  - `cad-lib migrate` command usage
  - Rollback procedure (downgrade to v2.8.x without losing user library)
- CHANGELOG.md template entry for v3.0.0 with all user-visible changes
- Post-install banner: `cad-lib doctor` prints on first run after upgrade
- Multi-version coexistence: v2.8 tolerates v3.0 `~/.cad-spec-gen/` files (ignore unknown keys)
- Telemetry: opt-in `cad-lib report --upload` stub (GitHub Discussions form target TBD)
- CI tiering: `@pytest.mark.slow` for Blender + HTTP tests, run only on main/nightly
- `pip install dist/*.whl && cad-lib list textures` post-build smoke test
- Release notes mechanism — who writes them, where they live, how they're promoted

### §20 AI Enhancement × PBR Conflict Resolution — BLOCKING

Must cover:
- Per-material AI enhance toggle: materials with normal map → AI denoise ≤0.2, pass normal/roughness as ControlNet hints
- Alternative: dual render (clean scalar → AI, detailed PBR → final); pick one lane
- Multi-view consistency strategy — how to prevent AI from re-hallucinating micro-structure per frame
- Feature flag: `CAD_SPEC_GEN_AI_ENHANCE_PBR_MODE={aoff|low_denoise|dual_render}` with default `low_denoise`
- Test fixture: render same part from 3 views with PBR + AI enhance, assert texture stability via SSIM > 0.95 across views

## 7. Files That Will Eventually Be Touched (Indicative, Not Committed)

When Spec 2 is implementation-ready, it will modify/add (subject to §16-§20 design completion):

- `src/cad_spec_gen/data/python_tools/render_3d.py` — PBR texture loading via new `_try_load_texture_maps()`
- `src/cad_spec_gen/data/python_tools/render_config.py` — three-tier material merge, `texture_group` field, lighting modes
- `src/cad_spec_gen/data/python_tools/parts_routing.py` — extended route() for full YAML rule support (extending Spec 1 interface)
- `codegen/gen_parts.py` — auto-routing via `parts_routing.route()`
- `cad_spec_reviewer.py` — Phase R dimension E
- `templates/design_review_template.md` — section E template
- `tools/cad_lib.py` — extended verbs (install/add/remove/sync/apply-review/trust/audit)
- `catalogs/library_manifest.yaml` — NEW (signed)
- `catalogs/library_manifest.yaml.sig` — NEW (signature)
- `catalogs/materials_aliases.yaml` — NEW (Chinese material aliases)
- `catalogs/gb_iso_equivalence.yaml` — NEW (GB/T ↔ ISO fasteners)
- `parts_library.default.yaml` — `template_routing` section
- Additional templates based on 3D designer + end-user feedback (powder_coat materials, possibly more bracket/housing variants)
- `docs/migration/v2.8-to-v3.0.md` — NEW migration guide
- `docs/quickstart/adding-your-first-template.md` — NEW walked example

Plus extensive test additions per the QA review.

## 8. Explicit Deferrals and Risks

### 8.1 Deferred to Post-Spec-2 (v3.1+)

- Model library (`~/.cad-spec-gen/shared/models/`) — NEMA motor families, etc. Not enough real designs.
- `cad-lib sync` remote manifest refresh — future, once §16 signing is stable
- Automatic `cad-lib report --upload` telemetry — future, requires server infrastructure
- Template community contribution workflow — future, requires §16 maintainer key management

### 8.2 Known Risks

| Risk | Mitigation path |
|------|----------------|
| §16 Security Model is large and unfamiliar work | Engage external security consultant; budget 2-3 weeks for threat modeling + signing infrastructure design |
| §17 Chinese keyword expansion requires real BOM data | Collect from partner firms; anonymize; target 500+ entries before implementation |
| §18 PBR physics requires Blender expertise | Pair with a 3D artist during implementation; visual regression suite against hand-curated golden renders |
| §19 v3.0 migration will break users who ignore release notes | Extensive pre-release beta period; post-install banner; support FAQ in advance |
| Spec 2 scope creeps back into "one big spec" | This §0 status banner; strict refusal to implement sections §16-§20 without full design completion |

## 9. Next Steps (for when Spec 2 becomes implementation-ready)

1. Spec 1 must ship and stabilize
2. Draft §16 Security Model in full (separate working doc acceptable)
3. Collect real BOM data and draft §17 Chinese Keyword Expansion
4. Validate §18 PBR Physics Corrections with a 3D artist (render comparisons before vs after)
5. Draft §19 Release Engineering including full migration guide
6. Draft §20 AI Enhancement × PBR Conflict Resolution
7. Re-run multi-perspective review on the expanded Spec 2 (the same 8 roles) to catch new issues
8. If clean → invoke `writing-plans` skill for Spec 2 implementation plan

---

**End of Spec 2 — Asset Library (Deferred Skeleton).**

This spec is a roadmap, not an implementation plan. It will not be executed as-is. The next concrete action is shipping Spec 1.
