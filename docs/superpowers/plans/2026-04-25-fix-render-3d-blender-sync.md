# Fix render_3d.py Blender Working Copy Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `cad/end_effector/render_3d.py`（Blender 实际运行副本）同步到 `src/cad_spec_gen/render_3d.py`（含 A1 全部功能的 canonical 版本），使 F4 回归断言从 ❌ 变 ✅。

**Architecture:** 项目维护两份 `render_3d.py`：`src/cad_spec_gen/render_3d.py` 是含 A1 功能的 canonical source（测试针对它），`cad/end_effector/render_3d.py` 是 Blender 执行副本（被 `tools/render_regression.py` 的 `_RENDER_SCRIPT` 引用）。Session 27 已经实现了 A1 功能，但 Blender 副本从未同步，导致 F4 fail：render_3d.py 不读 `CAD_RUNTIME_MATERIAL_PRESETS_JSON`，`create_pbr_material()` 也不支持贴图节点。修复 = 把 canonical 版本复制到 Blender 副本路径。

**Tech Stack:** Python 3.11+, Blender 4.x, pytest, `tools/render_regression.py`

---

### Task 0: 确认现有测试当前状态（RED 基线）

**Files:**
- Read: `src/cad_spec_gen/render_3d.py`
- Read: `cad/end_effector/render_3d.py`

- [ ] **Step 1: 运行结构性测试，确认 canonical 版本全绿**

```bash
uv run pytest tests/test_render_3d_structure.py tests/test_render_3d_texture_bridge.py tests/test_render_3d_texture_path.py -v 2>&1 | tail -20
```

期望：`PASSED` — 全部通过（针对 `src/cad_spec_gen/render_3d.py`）

- [ ] **Step 2: 确认两文件行数差异（证明副本确实是旧版）**

```bash
wc -l src/cad_spec_gen/render_3d.py cad/end_effector/render_3d.py
```

期望：src 版本 ~1040 行，cad 版本 ~813 行，差 ~227 行

---

### Task 1: 同步 Blender 副本（GREEN）

**Files:**
- Modify: `cad/end_effector/render_3d.py` ← 以 `src/cad_spec_gen/render_3d.py` 为源

- [ ] **Step 1: 备份旧副本（可选 diff，仅供查阅）**

```bash
diff src/cad_spec_gen/render_3d.py cad/end_effector/render_3d.py | head -60
```

预期看到缺失的 `_resolve_texture_path`、`_detect_normal_convention`、runtime override 加载块、`create_pbr_material` 中的 A1-2 纹理桥段落。

- [ ] **Step 2: 复制 canonical 版本到 Blender 副本路径**

```bash
cp src/cad_spec_gen/render_3d.py cad/end_effector/render_3d.py
```

预期：命令无报错，`cad/end_effector/render_3d.py` 行数变为 ~1040。

- [ ] **Step 3: 验证复制成功**

```bash
wc -l cad/end_effector/render_3d.py
diff src/cad_spec_gen/render_3d.py cad/end_effector/render_3d.py
```

期望：行数相同，diff 无输出。

---

### Task 2: 验证测试仍全绿（无回归）

**Files:**
- Test: `tests/test_render_3d_structure.py`
- Test: `tests/test_render_3d_texture_bridge.py`
- Test: `tests/test_render_3d_texture_path.py`
- Test: `tests/test_render_config_runtime_override.py`

- [ ] **Step 1: 运行 render 相关测试**

```bash
uv run pytest tests/test_render_3d_structure.py tests/test_render_3d_texture_bridge.py tests/test_render_3d_texture_path.py tests/test_render_config_runtime_override.py -v 2>&1 | tail -30
```

期望：全部 PASSED，0 FAILED。

- [ ] **Step 2: 运行全量测试（排除 blender smoke）**

```bash
uv run pytest -m "not blender" --tb=short -q 2>&1 | tail -20
```

期望：之前跑通的数量（≥ 1209 passed）不减少，0 FAILED。

---

### Task 3: 端到端 dry-run 验证（render_regression 前置检查）

**Files:**
- Read: `tools/render_regression.py`

- [ ] **Step 1: dry-run 模式确认管线参数正确**

```bash
uv run python tools/render_regression.py --dry-run 2>&1 | head -40
```

期望：
- `[preflight] Blender: ...` — Blender 路径找到
- `[preflight] GLB: ...` — GLB 文件找到
- `[render] 命令: blender ... cad/end_effector/render_3d.py ...` — 路径引用更新后的副本
- `[render] env CAD_RUNTIME_MATERIAL_PRESETS_JSON=...` — enhanced 模式注入 env
- `[render] --dry-run 模式，跳过实际渲染`

---

### Task 4: 实际渲染 + F4 断言验证（最终验收）

**Files:**
- Artifact: `artifacts/regression/`

- [ ] **Step 1: 清理旧产物（避免 F4 用旧 PNG 比较）**

```bash
rm -rf artifacts/regression/baseline artifacts/regression/enhanced
```

- [ ] **Step 2: 运行完整渲染回归（预计 5-15 分钟，取决于 GPU）**

```bash
uv run python tools/render_regression.py 2>&1 | tee artifacts/regression/run_log.txt | tail -30
```

期望：
- `[render] ✅ 渲染完成`（baseline 和 enhanced 各一次）
- `F1 ✅`：runtime_materials.json 含 base_color_texture
- `F2 ✅`：SW_TEXTURES_DIR 目录存在
- `F4 ✅`：enhanced PNG 大小 > baseline 5%（这是本次修复的核心目标）
- `F5 ✅`：所有 PNG 非全黑

- [ ] **Step 3: 查看完整报告**

```bash
cat artifacts/regression/report.md
```

确认 F4 行显示 ✅ 及正的百分比（enhanced 渲染了纹理，文件更大）。

---

### Task 5: 提交

**Files:**
- Commit: `cad/end_effector/render_3d.py`

- [ ] **Step 1: 确认变更范围**

```bash
git diff --stat cad/end_effector/render_3d.py
```

期望：只有 `cad/end_effector/render_3d.py` 有改动。

- [ ] **Step 2: Commit**

```bash
git add cad/end_effector/render_3d.py
git commit -m "$(cat <<'EOF'
fix(render): 同步 Blender 副本 render_3d.py 补齐 A1 纹理桥

cad/end_effector/render_3d.py 从未同步 src/cad_spec_gen/render_3d.py
的 A1 功能，导致回归工具 F4 持续 fail。补齐：
- _resolve_texture_path / _detect_normal_convention helpers
- runtime preset override 加载块（CAD_RUNTIME_MATERIAL_PRESETS_JSON）
- create_pbr_material A1-2 贴图桥（ShaderNodeTexImage + BOX 投影）
- assign_materials 使用 _MATERIAL_PRESETS_RUNTIME 而非 MATERIAL_MAP

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## 自审检查

**Spec coverage：**
- [x] F4 根因 1（不读 env）→ Task 1 同步后 runtime override 块进入副本
- [x] F4 根因 2（不支持贴图节点）→ Task 1 同步后 create_pbr_material A1-2 进入副本
- [x] 无回归 → Task 2 全量测试
- [x] 端到端验证 → Task 4 render_regression F4 ✅

**Placeholder scan：** 无 TBD / TODO / "类似 Task N" 等占位语。

**Type consistency：** 无新增类型，仅文件同步。
