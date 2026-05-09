# photo3d-autopilot 自动检测 jury config（A1.1 子集）设计文档

**作者**：proecheng
**日期**：2026-05-09
**状态**：spec 待审
**前置 spec**：`2026-05-09-photo3d-jury-v2-handoff-integration-design.md`（v2.28.0 已发布）
**关联 §**：v2.28.0 spec §2.2"v1.3 把 autopilot 文案变更全部移出范围（推到 A1.1 独立 PR）"

---

## 修订历史

| 版本 | 日期 | 变更 |
|---|---|---|
| 1.0 | 2026-05-09 | 初稿（brainstorm 4 决策点收敛后落盘）|

---

## 1. 背景与北极星对齐

### 1.1 v2.28.0 后断点

v2.28.0 已落 `photo3d-handoff --with-jury` 一条命令跑闭环。但用户进入此命令的路径仍需要"知道有这个命令存在"——`photo3d-autopilot` 当前 `ready_for_enhancement` 状态推荐的是 `enhance` 单跑命令，不引导用户走 jury 闭环。

外行用户的真实体验：
1. 跑 `photo3d-autopilot --subsystem X` 看下一步
2. autopilot 输出 `next_action.argv = ["python", "cad_pipeline.py", "enhance", ...]`
3. 用户按推荐跑 `enhance` → 跑完后还得**自己想到**要再跑 `enhance-check` + `photo3d-jury` + `enhance-review`
4. 北极星"傻瓜式"破：用户必须记得多步流程，autopilot 不引导

### 1.2 北极星 5 gate 对齐

| Gate | 提升点 |
|---|---|
| 零配置 | autopilot 静默检测 `~/.claude/cad_jury_config.json`；未配用户行为完全不变 |
| 稳定可靠 | helper 是 silent boolean 探针；任何失败 fallback 推荐 enhance（v2.27.0 行为）|
| 结果准确 | 已配 jury 用户自动获得 `--with-jury` 闭环推荐，避免"忘了跑 jury"导致 deliver 缺正式契约 |
| SW 装即用 | 无 SW 涉及 |
| 傻瓜式操作 | 已配 jury 用户从 autopilot 一步到 handoff 一条龙；少打 3 个命令 |

### 1.3 已收敛决策点（brainstorm session 摘要）

- **触发条件**：自动检测 `~/.claude/cad_jury_config.json` 是否存在 + 合法（不加 cli flag）
- **检测策略**：中等检测（文件存在 + JSON 解析 + 含 active_profile_id 字段 + active_profile_id 在 profiles[].id 列表中）
- **失败 fallback**：silent fallback 到现有 `enhance` 推荐路径（v2.27.0 行为完全保持；不写 stderr）
- **schema 方案**：方案 ② 加新 `next_action.kind = "run_handoff_with_jury"` 枚举值（add-only）；`status` 字段保持 `ready_for_enhancement` 不变
- **opt-out**：不加 cli flag；用户想关 jury 自己删 config（最傻瓜式假设）

---

## 2. 范围与非目标

### 2.1 范围（in-scope）

1. `tools/photo3d_autopilot.py` 加 `_jury_config_available(home_dir: Path | None = None) -> bool` 模块级 helper
2. `tools/photo3d_autopilot.py` 加 module-level 常量 `JURY_CONFIG_PATH: Path = Path.home() / ".claude" / "cad_jury_config.json"`（可被测试 monkeypatch override）
3. `tools/photo3d_autopilot.py:_next_action` 在 `ready_for_enhancement` 分支末尾调 `_jury_config_available()` 决定 next_action.kind / argv
4. 检测 True：next_action 改为：
   - `kind = "run_handoff_with_jury"`（新枚举值）
   - `argv = [sys.executable, "cad_pipeline.py", "photo3d-handoff", "--subsystem", X, "--with-jury", "--confirm"]`
   - 不带 `default_provider_preset` / `provider_presets`（这些是 enhance 子命令字段）
5. 检测 False：现有 enhance 推荐路径完全不变（v2.27.0 行为保持）
6. 测试 `tests/test_cad_pipeline_autopilot.py` 加 5+ 集成用例 + 新建 `tests/test_photo3d_autopilot_jury_detection.py` 含 9 helper 单测
7. 文档 `docs/cad-jury-config.md` 加段落"autopilot 自动检测 jury config"

### 2.2 非目标（out-of-scope）

- ❌ 不加 cli flag（`photo3d-autopilot --with-jury` / `--no-jury`）：spec rev 1.0 brainstorm 拍板"纯自动 无 flag"
- ❌ 不改 `status` 字段枚举值：保持 `ready_for_enhancement`（不引入新 status 状态）
- ❌ 不改其他 `_next_action` 状态分支（blocked / accept_baseline / 三态 enhancement_summary）
- ❌ 不改 `photo3d-handoff` 自身（v2.28.0 已落；handoff 自己 step 0.5 fail-fast preflight 是真守门）
- ❌ 不改 `PHOTO3D_AUTOPILOT.json` schema_version（add-only kind 枚举值不需升 schema_version；按 jury v1 invariant 14 add-only 兼容性宪章）
- ❌ 不读 jury config 中的 `api_key` / `base_url` / `model` 字段（防潜在泄漏；只读 `active_profile_id` + `profiles[].id` 做存在性校验）

### 2.3 非目标的兼容性承诺

- 未配 jury config 用户：autopilot 行为 100% 与 v2.27.0 一致
- 已配 jury config 用户：next_action.kind 改为新枚举；下游消费者用 `.get("kind")` 模式（参 v2.28.0 §7.2 钉死的 `.get()` 兼容契约）自动兼容
- `photo3d-autopilot --subsystem X` cli 不引入新参数；用户调用方式不变

---

## 3. 架构

### 3.1 上下文图

```
photo3d-autopilot --subsystem X
        │
        ▼
build_photo3d_autopilot_report → _next_action
        │
        ├─ gate_status="blocked" ─▶ follow_action_plan (现有不变)
        ├─ accepted_baseline is None ─▶ accept_baseline (现有不变)
        ├─ enhancement_summary 存在 ─▶ delivery_complete / preview / blocked (现有不变)
        └─ ready_for_enhancement 默认分支:
              │
              ▼
        NEW: with_jury = _jury_config_available()  # silent boolean 探针
              │
              ├─ True  → kind="run_handoff_with_jury"
              │         argv = [..., "photo3d-handoff", "--with-jury", "--confirm"]
              └─ False → kind="run_enhancement" (现有不变)
                       argv = [..., "enhance", ...] (现有不变)
              │
              ▼
        status = "ready_for_enhancement"（两路径同 status；by kind 区分）
```

### 3.2 文件布局

```
tools/photo3d_autopilot.py            ← 加 JURY_CONFIG_PATH 常量 + _jury_config_available helper +
                                       _next_action ready_for_enhancement 分支扩展（~50 行 add-only）
tests/test_photo3d_autopilot_jury_detection.py（新文件，~150 行）
                                      含 9 helper 单测（覆盖文件不存在 / JSON 损坏 / 字段缺失 / typo / OSError）
tests/test_cad_pipeline_autopilot.py   ← 加 5+ 集成用例 + 回归守门（~80 行 add-only）
docs/cad-jury-config.md                ← 加段落"autopilot 自动检测 jury config"（~15 行）

注：tools/photo3d_handoff.py 与 jury 子模块全部 0 改动（A1 v2.28.0 已落）。
```

### 3.3 模块契约

| 模块 / 函数 | 单一职责 | 输入 | 输出 | 不做 |
|---|---|---|---|---|
| `JURY_CONFIG_PATH`（module 常量）| 默认 jury config 路径 | n/a | `Path.home() / ".claude" / "cad_jury_config.json"` | 测试可 monkeypatch override |
| `_jury_config_available(home_dir=None) -> bool` | silent boolean 探针：检测 jury config 是否存在 + 合法 | 可选 home_dir 参数（测试用） | True iff 文件存在 + 合法 JSON dict + active_profile_id 字符串非空 + 在 profiles[].id 中 | 不发 HTTP / 不调 LLM / 不调 subprocess / 不写盘 / 不抛异常 / 不读 api_key/base_url/model |
| `_next_action`（修改） | 在 ready_for_enhancement 分支末尾调 `_jury_config_available()` 决定 kind/argv | 同现有 | 同现有；ready_for_enhancement 路径下 next_action.kind ∈ {`run_enhancement`, `run_handoff_with_jury`} | 不改其他状态分支 |

### 3.4 不变量

1. **silent boolean 探针**：`_jury_config_available()` 任何失败路径返 False；不抛异常 / 不写 stderr / 不影响 autopilot 主流程
2. **pure read-only**：仅 `path.is_file()` + `path.read_text()` + `json.loads()`；无写盘 / 无 subprocess / 无 HTTP / 无锁
3. **不读敏感字段**：仅校验 `active_profile_id` 字段 + `profiles[].id` 列表；**禁止** 读取 `api_key` / `base_url` / `model` / `cost_per_call_usd` 等字段（防潜在泄漏向量）
4. **add-only schema**：next_action.kind 加新枚举值 `run_handoff_with_jury`；不删既有 `run_enhancement`；`PHOTO3D_AUTOPILOT.json` schema_version 不升
5. **status 字段不变**：`ready_for_enhancement` 状态在两路径（with/without jury）下都用同一 status；不引入新 status 枚举
6. **未配用户零感知**：`_jury_config_available()` 返 False 时 autopilot 主流程完全等同 v2.27.0；现有测试 0 break
7. **autopilot 仍 gate-only**：本 PR 不让 autopilot 调任何 subprocess / 不实跑 enhance / 不实跑 jury
8. **handoff 真守门**：autopilot 检测仅 advisory；用户跑 `photo3d-handoff --with-jury` 时由 handoff 自身 step 0.5 fail-fast preflight 真校验 jury config（autopilot 检测时合法但用户跑前删了 / 改坏了由 handoff 兜底）
9. **encoding 强制**：helper 内 `path.read_text(encoding="utf-8")` 强制；防 Windows 中文 zh-CN GBK 默认编码下读 jury config 含中文 reason 时炸（沿用 jury v1 invariant 12）
10. **`Path.home()` 失败保护**：内部 try/except RuntimeError → return False（罕见但有定义）

---

## 4. 数据流

### 4.1 完整流程

```
photo3d-autopilot --subsystem X
        │
        ▼
读 ARTIFACT_INDEX.json + PHOTO3D_REPORT.json (现有不变)
        │
        ▼
build_photo3d_autopilot_report (现有不变)
  active_run_id / gate_status / accepted_baseline / enhancement_summary
        │
        ▼
_next_action(...) (修改 ready_for_enhancement 分支末尾)
        │
        ├─ gate_status == "blocked" → return ("blocked", follow_action_plan)
        ├─ accepted_baseline is None → return ("needs_baseline_acceptance", accept_baseline)
        ├─ enhancement_summary 存在
        │     ├─ delivery_status == "accepted" → ("enhancement_accepted", delivery_complete)
        │     ├─ "preview" → ("enhancement_preview", review_enhancement_preview)
        │     └─ "blocked" → ("enhancement_blocked", fix_enhancement_blockers)
        ▼ ready_for_enhancement 默认分支
        │
        ▼
[NEW] with_jury = _jury_config_available()  # silent
        │
        ├─ with_jury == True
        │      argv = [sys.executable, "cad_pipeline.py", "photo3d-handoff",
        │              "--subsystem", subsystem, "--with-jury", "--confirm"]
        │      action = {
        │        "kind": "run_handoff_with_jury",
        │        "requires_user_confirmation": False,
        │        "argv": argv,
        │      }
        │      if _safe_cli_token(subsystem):
        │          action["cli"] = " ".join(argv)
        │      return ("ready_for_enhancement", action)
        │
        └─ with_jury == False (v2.27.0 路径不变)
               argv = [sys.executable, "cad_pipeline.py", "enhance", "--subsystem", subsystem, "--dir", render_dir]
               action = {
                 "kind": "run_enhancement",
                 "requires_user_confirmation": False,
                 "argv": argv,
                 "default_provider_preset": DEFAULT_PROVIDER_PRESET,
                 "provider_presets": public_provider_presets(),
               }
               if _safe_cli_token(subsystem) and render_dir:
                   action["cli"] = " ".join(argv)
               return ("ready_for_enhancement", action)
```

### 4.2 `_jury_config_available()` 内部数据流

```
_jury_config_available(home_dir: Path | None = None) -> bool:
    try:
        config_path = (home_dir or Path.home()) / ".claude" / "cad_jury_config.json"
    except RuntimeError:
        return False  # Path.home() 罕见失败

    if not config_path.is_file():
        return False

    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError:
        return False

    try:
        config = json.loads(text)
    except json.JSONDecodeError:
        return False

    if not isinstance(config, dict):
        return False

    profile_id = config.get("active_profile_id")
    if not isinstance(profile_id, str) or not profile_id:
        return False

    profiles = config.get("profiles")
    if not isinstance(profiles, list) or not profiles:
        return False

    return any(
        isinstance(p, dict) and p.get("id") == profile_id
        for p in profiles
    )
```

注：仅最外层无 catch-all `except Exception`；每个失败点精准 catch（OSError / JSONDecodeError / RuntimeError / type 校验）。

---

## 5. 错误处理

### 5.1 错误分类

| 失败场景 | 行为 |
|---|---|
| `~/.claude/cad_jury_config.json` 不存在 | `is_file()` False → return False |
| 文件存在但权限错（OSError）| try/except OSError → return False |
| JSON 解析失败 | try/except json.JSONDecodeError → return False |
| 顶层不是 dict（如 list / 数字 / 字符串）| `isinstance(config, dict)` False → return False |
| 缺 `active_profile_id` 字段或非字符串或空 | return False |
| 缺 `profiles` 字段或非 list 或空 | return False |
| `active_profile_id` 不在 `profiles` 任何 `id` 中（typo / 失配）| return False |
| `Path.home()` 抛 RuntimeError | try/except RuntimeError → return False |

### 5.2 安全网

- helper 内部最外层各 try/except 精准 catch；**禁止** `except Exception`（过宽；可能掩盖编程错误如 AttributeError）
- 检测失败 → autopilot 仍按现有 ready_for_enhancement 路径推荐 enhance；用户零感知

### 5.3 与 photo3d-handoff 的交互

- autopilot 检测是 advisory（不锁结果）
- handoff 自身 step 0.5 fail-fast preflight 是真守门（v2.28.0 已落 H20 用例守门）
- 边界场景：autopilot 检测时 jury config 合法 → 推荐 handoff；用户跑前 jury config 损坏 / 删了 → handoff fail-fast 报 `handoff_jury_preflight_config_missing`（exit=2 + 中文文案引导用户重新配 config）

---

## 6. 测试策略

### 6.1 TDD 铁律

每用例 RED → GREEN → REFACTOR → Commit。CLAUDE.md 强制。

### 6.2 单元测试 — `_jury_config_available` helper

新文件 `tests/test_photo3d_autopilot_jury_detection.py`（~150 行）：

| 测试 | 预期 |
|---|---|
| `test_jury_config_missing_returns_false` | 文件不存在 → False |
| `test_jury_config_valid_returns_true` | 合法配置（含 active_profile_id + 匹配 profile）→ True |
| `test_jury_config_corrupt_json_returns_false` | 文件存在但损坏 JSON → False |
| `test_jury_config_top_level_not_dict_returns_false` | 顶层是 list / str / int → False |
| `test_jury_config_missing_active_profile_id` | 缺字段 / 空字符串 / 非字符串 → False |
| `test_jury_config_missing_profiles_list` | 缺 / 空 / 非 list → False |
| `test_jury_config_active_profile_id_not_in_profiles` | typo → False |
| `test_jury_config_oserror_silent` | mock `read_text` 抛 OSError → False（不抛）|
| `test_jury_config_does_not_read_secrets` | inspect.getsource 验证 helper 实现不引用 api_key / base_url / model 字段名 |

### 6.3 集成测试 — `_next_action` ready_for_enhancement 分支

追加 `tests/test_cad_pipeline_autopilot.py`（~80 行）：

| 测试 | 预期 |
|---|---|
| `test_ready_for_enhancement_with_jury_config_recommends_handoff` | jury config 合法 → next_action.kind="run_handoff_with_jury" / argv 含 `--with-jury` `--confirm` |
| `test_ready_for_enhancement_no_jury_config_recommends_enhance` | jury config 缺失 → kind="run_enhancement"（v2.27.0 regression）|
| `test_ready_for_enhancement_invalid_jury_config_falls_back_to_enhance` | jury config 损坏 → fallback enhance |
| `test_status_remains_ready_for_enhancement_both_paths` | 两路径 status 都是 "ready_for_enhancement" |
| `test_argv_uses_safe_cli_token_for_subsystem_with_special_chars` | 特殊字符 subsystem → action 不含 cli 字段（仅 argv） |
| `test_other_states_not_affected` | blocked / accept_baseline / 三态 enhancement_summary 路径不触发 jury 检测 |

### 6.4 Mock 策略

- 所有用例用 `monkeypatch.setattr` patch `tools.photo3d_autopilot.JURY_CONFIG_PATH` 指向 tmp_path 内的 fake config（避免污染真实 home dir）
- helper 测试 fixture 工厂 `make_jury_config(state)` 状态枚举：`ok` / `missing` / `corrupt` / `top_level_list` / `no_active_id` / `orphan_id` / `oserror`

### 6.5 不写的测试（YAGNI 边界）

- 不测真实 `Path.home()` resolve（用 monkeypatch override 常量）
- 不测真实 jury config 文件读（fixture 工厂构造）
- 不测真实 LLM 调用（autopilot 不调 LLM；helper pure read-only）

### 6.6 CI 矩阵

- Linux + Windows 都跑（`Path.home()` + `monkeypatch.setenv("HOME"|"USERPROFILE")` 兼容）
- mypy strict 必过（jury v1 已上 strict gate；本 PR 改的所有文件保持 strict）
- ruff check + format 必过

---

## 7. 兼容性与迁移

### 7.1 cli 层

- `photo3d-autopilot --subsystem X` 命令格式不变；不引入新 cli 参数
- 用户调用方式 100% 一致

### 7.2 报告 schema

- `PHOTO3D_AUTOPILOT.json` schema_version 不升（按 jury v1 invariant 14 add-only 兼容性宪章）
- 现有字段集严格保持
- `next_action.kind` 字段加新枚举值 `run_handoff_with_jury`；现有 `run_enhancement` / `accept_baseline` / 等保持

### 7.3 消费方读取契约

下游消费者（photo3d-handoff cli / 用户脚本 / CI）读 `next_action.kind` 时：
- 推荐用 `dict.get("kind", "")` 模式 + 显式 enum 列表（参 v2.28.0 §7.2 钉死的 `.get()` 兼容契约）
- 不识别 `run_handoff_with_jury` 的旧消费者（如 v2.27.0 之前的脚本）：fallback 推荐用户复制粘贴 `next_action.cli` 字符串（仍是合法 cli 命令）

### 7.4 配置

- `~/.claude/cad_jury_config.json`：完全不变（v1 配置直接被 autopilot 检测）
- 不引入新环境变量 / 新文件

### 7.5 文档迁移

- `docs/cad-jury-config.md` 加段落"autopilot 自动检测 jury config 行为"
- `docs/PROGRESS.md` 加 v2.29.0 入口

---

## 8. 实施顺序（plan 阶段拆分预想）

预估 plan 阶段会拆 ~6-8 task。粗顺序：

1. **C0 准备**：建分支（已建）+ spec commit
2. **C1 helper 单测**：写 9 helper 单测 RED → 实现 `_jury_config_available` + `JURY_CONFIG_PATH` 常量 → GREEN → 单 commit
3. **C2 _next_action 集成**：写 5+ 集成测试 RED → 改 `_next_action` ready_for_enhancement 分支调 helper → GREEN → 单 commit
4. **C3 回归守门**：写 `test_other_states_not_affected` + 现有 autopilot 测试不破 → 单 commit
5. **C4 文档**：docs/cad-jury-config.md / docs/PROGRESS.md 更新 → 单 commit
6. **C5 全量回归 + ruff/mypy + 北极星 5 gate 体检** → 单 commit
7. **C6 PR + tag v2.29.0 + GitHub Release**

每 C 段一个 commit；先 RED 后 GREEN。

---

## 9. 风险与已知 unknown

### 9.1 已知风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| home dir mock 在 Windows / Linux 行为差异 | 测试 flake | monkeypatch JURY_CONFIG_PATH 常量直接（不 mock Path.home()）|
| jury config schema 在 jury v2 升级后字段变 | autopilot 检测假阳性/假阴性 | 仅校验 active_profile_id + profiles[].id（最稳 invariant；jury v1 v2 都不会改这两个字段）|
| 用户在 autopilot 检测后跑前删 / 改坏 jury config | autopilot 推荐 handoff 但 handoff fail | handoff 自身 step 0.5 fail-fast preflight 兜底（H20 用例守门）|
| 下游消费者不识别 `run_handoff_with_jury` | 旧脚本 break | next_action.cli 字段保持合法命令字符串；下游可直接复制粘贴 |
| mypy strict 下 helper 内 `config.get("profiles")` 类型推断为 Any | 隐式类型扩散 | 显式 `isinstance(profiles, list)` 守卫 + `cast(list, profiles)` 必要时 |

### 9.2 已知 unknown

- `Path.home()` 在某些 CI 环境（如 GitHub Actions runner）的实际值；需在测试中 monkeypatch override 而非依赖默认
- helper 9 测试的 fixture 工厂细节由 plan 阶段细化

### 9.3 不接受的风险（Red Team 防线）

- **不允许**：helper 读 api_key / base_url / model 等敏感字段（破坏 invariant 3）
- **不允许**：helper 抛异常向上（破坏 invariant 1 silent 探针）
- **不允许**：autopilot 调任何 subprocess（破坏 invariant 7 gate-only）
- **不允许**：改其他 _next_action 状态分支（破坏 invariant 6 未配用户零感知）
- **不允许**：改 PHOTO3D_AUTOPILOT.json schema_version（破坏 invariant 4 add-only 兼容性宪章）

---

## 10. 验收标准（DoD）

完成本 PR 必须满足：

1. **测试**：所有 §6 测试 PASS（9 helper 单测 + 6 集成测试 = 15 用例）
2. **回归**：`tests/` 全量 PASS 不少于 v2.28.0 基线（≥2706 PASS）
3. **mypy strict**：本 PR 改的所有文件保持 strict 不降级
4. **ruff check + format**：clean
5. **CI**：Linux + Windows 双平台全绿
6. **coverage**：本 PR 新加路径 ≥90% 覆盖
7. **文档**：
   - `docs/cad-jury-config.md` 加段落
   - `docs/PROGRESS.md` 加 v2.29.0 入口
   - 本 spec commit
8. **北极星 5 gate 体检**：
   - 零配置：✓ 静默检测；未配用户行为不变
   - 稳定可靠：✓ silent 探针；fallback 安全
   - 结果准确：✓ 已配用户自动获 jury 闭环推荐
   - SW 装即用：✓ 无 SW 涉及
   - 傻瓜式操作：✓ 一步从 autopilot 到 handoff 一条龙
9. **schema 钉死**：next_action.kind 仅在 ready_for_enhancement 状态下取值 ∈ {`run_enhancement`, `run_handoff_with_jury`}；其他 kind（`accept_baseline` / `follow_action_plan` / `delivery_complete` 等）保持现有
10. **PR 流程**：feat/autopilot-with-jury → PR → CI 全绿 → squash merge → tag v2.29.0 + GitHub Release

---

## 11. 后续 (v3 路线，不在本 PR)

- 将来 jury v2 加 `kind=anthropic_native` / `fallback_profile_ids` 等字段时，autopilot 检测无需改动（仍仅校验 active_profile_id 在 profiles[].id；前向兼容）
- 若用户反馈"想关 jury 但不想删 config"，下一 PR 加 `photo3d-autopilot --no-jury` opt-out flag

---

## 附录 A：参考文件

| 文件 | 用途 |
|---|---|
| `tools/photo3d_autopilot.py` | 现有 autopilot 实现；本 PR 在此 add-only |
| `tools/photo3d_handoff.py` | v2.28.0 已落；step 0.5 fail-fast preflight 真守门 jury config |
| `~/.claude/cad_jury_config.json` | jury v1 配置文件（用户配置） |
| `docs/superpowers/specs/2026-05-08-photo3d-jury-design.md` | jury v1 设计 / config schema |
| `docs/superpowers/specs/2026-05-09-photo3d-jury-v2-handoff-integration-design.md` | v2.28.0 spec（A1）|
| `CLAUDE.md` | 项目工作流约束（superpowers + TDD + 中文输出） |
