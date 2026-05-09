# jury §11 follow-up cleanup 设计文档（M-1 + M-2）

**作者**：proecheng
**日期**：2026-05-09
**状态**：spec 待审
**前置 spec**：`2026-05-09-photo3d-jury-v2-handoff-integration-design.md`（v2.28.0 已发布）+ `2026-05-09-autopilot-with-jury-design.md`（v2.29.0 已发布）
**关联**：v2.28.0 PR #61 Task 13 spec reviewer 标的 2 项 MINOR（M-1 + M-2），登记入 §11 follow-up 推迟到独立 PR。本 PR 闭这两项。

---

## 修订历史

| 版本 | 日期 | 变更 |
|---|---|---|
| 1.0 | 2026-05-09 | 初稿（brainstorm 2 决策点收敛后落盘）|

---

## 1. 背景与北极星对齐

### 1.1 §11 follow-up 来源

v2.28.0 PR #61 Task 13 spec reviewer 标 2 项 MINOR（不阻断 release，登记入 §11 follow-up）：

- **M-1**：spec §4.2 line 475 规定 `crashed_mid_orchestration` exit = "透传 KeyboardInterrupt=130 / OS 信号原值"，但实现 `command_return_code` 把它与 `internal_error` 合并到 99。**spec vs 实现二义**。
- **M-2**：`review_failed` 分支 fallback `else 23`（review_raw_exit 缺时）与 spec §4.2 line 460 "clamp_review_exit(review_raw)" 不完全等价，且 23 与 `review_input_corrupt` 撞码。**语义混淆**。

### 1.2 北极星 5 gate 影响

| Gate | M-1 影响 | M-2 影响 |
|---|---|---|
| 零配置 | 无 | 无 |
| 稳定可靠 | spec/实现二义 → 未来维护者困惑 | 撞码 → 用户从 exit code 看不出阶段 |
| 结果准确 | 边界场景 exit 含义不清 | review_failed vs corrupt 难分 |
| SW 装即用 | 无 | 无 |
| 傻瓜式操作 | 无 | 23 用户不懂是 review 失败还是输入坏 |

### 1.3 已收敛决策点（brainstorm session 摘要）

- **M-1**：**spec 改 99 + 加注释**说明 KeyboardInterrupt 走 Python 默认 130 路径不进 command_return_code；`crashed_mid_orchestration` 仅覆盖"主流程没崩但 jury hook 留 partial state"边界场景，99 合理。**实现不动**（line 254 `if jhs in ("internal_error", "crashed_mid_orchestration"): return 99` 保持）。
- **M-2**：**实现改 fallback 20**（review_failed clamp 段最低位，与 raw=1 同段；不与 review_input_corrupt 23 撞码）。spec §4.2 line 460 `clamp_review_exit(review_raw)` 字面继续生效；本 PR 在 spec 加细则说明 fallback 20 来源。

---

## 2. 范围与非目标

### 2.1 范围（in-scope）

1. 改 v2.28.0 spec `docs/superpowers/specs/2026-05-09-photo3d-jury-v2-handoff-integration-design.md`：
   - §4.2 line 475 改 `(透传 KeyboardInterrupt = 130 / OS 信号原值)` → `99（与 internal_error 同段）` + 加注释说明 KeyboardInterrupt 走 Python 默认路径
   - §4.2 line 460 `clamp_review_exit(review_raw)` 加注释说明 review_raw 缺时 fallback 20（review_failed 段最低位）
   - §11 列表加"M-1 / M-2 closed by v2.30.0"标记
2. 改 `tools/photo3d_handoff.py:command_return_code` line 247：
   - 当前 `return clamp_review_exit(raw) if isinstance(raw, int) else 23`
   - 改为 `return clamp_review_exit(raw) if isinstance(raw, int) else 20`
3. 加 2 个测试守门：
   - `test_command_return_code_review_failed_with_missing_raw_returns_20`：review_raw_exit 缺时返 20
   - `test_command_return_code_review_failed_with_non_int_raw_returns_20`：review_raw_exit 非 int（如 None / str）时返 20
4. 文档：`docs/PROGRESS.md` 加 v2.30.0 入口

### 2.2 非目标（out-of-scope）

- ❌ 不改 `crashed_mid_orchestration` 实现行为（本 PR 仅 spec 改注释）
- ❌ 不引入新 exit code 段（如 26）
- ❌ 不动 `clamp_review_exit` helper 签名 / 行为
- ❌ 不动其他 §11 follow-up 项（contract_io mypy 历史债推迟独立 PR）
- ❌ 不改 jury 子模块 / autopilot / 其他 cli

### 2.3 兼容性承诺

- 所有现有用户行为保持（M-1 实现现状不变；M-2 仅 review_raw_exit 缺时 23→20，**改善**：用户从 exit 能区分阶段）
- v2.28.0 / v2.29.0 测试 0 break
- spec schema 字段 / kind 枚举值 / status 字段全部保持

---

## 3. 架构

无新加组件；本 PR 仅 1 行代码 + 2 测试 + spec 注释。

### 3.1 改动分布

| 文件 | 改动 | 行数估计 |
|---|---|---|
| `docs/superpowers/specs/2026-05-09-photo3d-jury-v2-handoff-integration-design.md` | §4.2 决策表 2 行注释 + §11 标记 + 修订历史 v1.5 entry | +20 |
| `tools/photo3d_handoff.py:command_return_code` line 247 | fallback 23 → 20（1 行 diff） | +1 / -1 |
| `tests/test_photo3d_handoff_with_jury.py` | 加 2 测试守门 | +30 |
| `docs/PROGRESS.md` | 加 v2.30.0 入口 | +5 |

### 3.2 不变量

1. `crashed_mid_orchestration` 实现仍返 99（与 `internal_error` 同段；实现不动）
2. `clamp_review_exit(int) -> int` 签名 / 行为不动
3. `command_return_code` 其他分支全保留
4. exit code 段不引入新值（仍是 0/1/2/3/4/10/11/12/13/20/21/22/23/24/25/99）
5. spec schema 不动；jury_handoff_status 17 个字符串值钉死

---

## 4. 数据流

### 4.1 M-1 spec 改动

`docs/superpowers/specs/2026-05-09-photo3d-jury-v2-handoff-integration-design.md` §4.2 决策表第 14 行：

**改前**：
```
| (handoff 崩溃 mid-step) | * | n/a (skip) | crashed_mid_orchestration | (透传 KeyboardInterrupt = 130 / OS 信号原值) |
```

**改后**：
```
| (handoff 崩溃 mid-step) | * | n/a (skip) | crashed_mid_orchestration | 99 (与 internal_error 同段；详见注释) |
```

加表后注释：
```
**crashed_mid_orchestration exit code 注释（v2.30.0 修订）**：
- KeyboardInterrupt（用户 Ctrl-C）→ Python 不调 command_return_code，进程默认 exit=130
- SIGTERM / SIGKILL → 进程被强制终止，不调 command_return_code
- 其他主流程没崩但 jury hook 留 partial state（如 finally 块写完报告后 main 流程仍正常 return）→ command_return_code 看 jury_handoff_status="crashed_mid_orchestration" → 返 99（与 internal_error 同段）
- 故 spec rev 1.4 "透传 OS 信号原值" 在 v1.5 修订为 99（实现现状对齐；signal 透传由 Python 自然路径处理，不经过 command_return_code）
```

### 4.2 M-2 实现改动

`tools/photo3d_handoff.py:command_return_code` line 247：

**改前**：
```python
        if jhs == "review_failed":
            raw = report.get("review_raw_exit")
            return clamp_review_exit(raw) if isinstance(raw, int) else 23
```

**改后**：
```python
        if jhs == "review_failed":
            raw = report.get("review_raw_exit")
            # review_raw_exit 缺 / 非 int → fallback 20（review_failed clamp 段最低位）
            # 不用 23 防与 review_input_corrupt 撞码（spec §11 follow-up M-2 v2.30.0 修）
            return clamp_review_exit(raw) if isinstance(raw, int) else 20
```

### 4.3 M-2 spec 注释

`docs/superpowers/specs/2026-05-09-photo3d-jury-v2-handoff-integration-design.md` §4.2 决策表第 2 行加注释：

```
| accepted | * | failed | review_failed | clamp_review_exit(review_raw) |
```

加表后注释：
```
**review_failed exit code 注释（v2.30.0 修订 §11 M-2）**：
- review_raw_exit 是 int → clamp_review_exit 映射（0→0 / 1→20 / 2→21 / 3→22 / 其他→23）
- review_raw_exit 缺 / 非 int → fallback 20（review_failed clamp 段最低位；不与 review_input_corrupt 23 撞码）
```

---

## 5. 错误处理

无新错误路径；本 PR 仅修正现有路径的 fallback 行为。

---

## 6. 测试策略

### 6.1 加 2 测试守门

在 `tests/test_photo3d_handoff_with_jury.py` 末尾追加：

```python
# === v2.30.0 §11 follow-up M-2: review_failed fallback ===

def test_command_return_code_review_failed_with_missing_raw_returns_20() -> None:
    """v2.30.0 §11 M-2 — review_raw_exit 字段缺失 → fallback 20（不与 review_input_corrupt 23 撞码）"""
    from tools.photo3d_handoff import command_return_code
    report = {"jury_handoff_status": "review_failed"}  # 无 review_raw_exit
    assert command_return_code(report) == 20


def test_command_return_code_review_failed_with_non_int_raw_returns_20() -> None:
    """v2.30.0 §11 M-2 — review_raw_exit 非 int（None/str）→ fallback 20"""
    from tools.photo3d_handoff import command_return_code
    for raw in (None, "1", 1.5, [], {}):
        report = {"jury_handoff_status": "review_failed", "review_raw_exit": raw}
        assert command_return_code(report) == 20, f"review_raw_exit={raw!r} should fallback 20"
```

### 6.2 现有测试不破

- v2.28.0 H12 `test_h12_accepted_review_failed` 用 `review_raw_exit=1`，仍走 `clamp_review_exit(1)=20` 路径——本 PR 不影响（fallback 20 与正常路径 20 巧合相同，但语义不同）。

---

## 7. 兼容性与迁移

- `command_return_code` 现有签名保持
- `tools.photo3d_handoff` 公开 API 全保持
- spec schema_version 不升

---

## 8. 实施顺序（plan 阶段拆分预想）

预估 plan 阶段 1-2 task：

1. **C0 准备**：建分支（已建）+ spec commit
2. **C1 实现 + 测试**：改 line 247 fallback 23→20 + 加 2 测试守门 + spec §4.2 注释 + §11 标记 + 修订历史
3. **C2 文档 + PR**：PROGRESS.md v2.30.0 + push + PR + tag

---

## 9. 验收标准（DoD）

1. **测试**：所有新加 2 测试 + 现有 H12 PASS
2. **回归**：`tests/` 全量 PASS 不少于 v2.29.0 基线（≥2723 PASS）
3. **mypy strict + ruff clean**（本 PR 改的文件）
4. **CI**：Linux + Windows 全绿
5. **文档**：v2.28.0 spec §4.2 注释 + §11 标记 closed + PROGRESS v2.30.0 入口
6. **PR 流程**：feat/jury-followup-cleanup → PR → CI 全绿 → squash merge → tag v2.30.0 + Release

---

## 附录 A：参考文件

| 文件 | 用途 |
|---|---|
| `tools/photo3d_handoff.py:command_return_code` line 247 | M-2 fallback 修正点 |
| `docs/superpowers/specs/2026-05-09-photo3d-jury-v2-handoff-integration-design.md` §4.2 | M-1 + M-2 spec 决策表 |
| `tests/test_photo3d_handoff_with_jury.py` | 加 2 测试守门 |
| `docs/PROGRESS.md` | v2.30.0 入口 |
