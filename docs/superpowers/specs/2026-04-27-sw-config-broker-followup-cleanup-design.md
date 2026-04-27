# sw_config_broker §11 follow-up cleanup（M-3/M-6/M-7/M-8/I-4 收官）设计 spec

- 版本：rev 1
- 创建：2026-04-27
- 模块：`adapters/solidworks/sw_config_broker.py`（含上下游 spec 与 CI 配置）
- 目标 PR：v2.21.1（patch）
- 前置 PR：[v2.21.0 (PR #21) M-2/M-4 cleanup](2026-04-27-sw-config-broker-m2-m4-cleanup-design.md)（forward link：该文件由 PR #21 创建，main merge 后路径稳定生效）
- 类型：§11 follow-up cleanup

---

## §1 背景 + 范围

PR #21（v2.21.0）关闭 §11 中 M-2 / M-4 后，`2026-04-26-sw-toolbox-config-list-cache-design.md`
§11 仍 open 7 项：M-1 / M-3 / M-5 / M-6 / M-7 / M-8 / I-4。

本 PR 收官其中 5 项（**M-3 / M-6 / M-7 / M-8 / I-4**），剩余 3 项（M-1 fsync / M-5 timeout
公式 / M-9 CI gate trace）推迟到独立 PR——这两项涉及真持久化语义改动 + 真行为基线
重测，scope 与本 cleanup PR 风格不一致。

### §1.1 范围分类

| 类型 | 项 | 说明 |
|---|---|---|
| 真改代码 | M-6 | 函数级 import → 模块级（`detect_solidworks` + `sw_config_lists_cache`） |
| 真改代码 | M-7 | `_validate_cached_decision` 返回类型用 `Literal[...]` 替代 `str`，删除 `_move_decision_to_history` 头部运行时校验 |
| 真改代码 | M-8 | cached decision 失效路径加 `assert invalid_reason is not None`（caller 侧 None guard） |
| CI 新增 | — | mypy strict gate，scope 仅 `adapters/solidworks/sw_config_broker.py`（渐进式 typing 政策） |
| 文档化 | M-3 | `_PROJECT_ROOT_FOR_WORKER` 模块级 vs 函数级 import 不对称——line 451-452 注释已充分 trace，**零代码改动** |
| 文档化 | I-4 | mtime+size collision 极罕见——`_envelope_invalidated` 附近加 1 行已知限制注释 |

### §1.2 北极星 5 gate 对齐

| Gate | 本 PR 影响 |
|---|---|
| 零配置 | 无影响（refactor + 文档） |
| 稳定可靠 | ✅ M-7 编译期类型保证 + M-8 显式契约断言 提升 |
| 结果准确 | 无影响（行为不变） |
| SW 装即用 | 无影响 |
| 傻瓜式操作 | 无影响 |

### §1.3 不在范围（明确排除）

- M-1 fsync 缺失——独立 PR（持久化语义真改，需 power-loss 测试基线）
- M-5 prewarm timeout 公式——独立 PR（需本机真 SW 实测重新校准）
- M-9 CI gate trace——纯文档已在 PR #21 spec 注释化，不重复
- 其他 mypy 模块进 strict——按渐进式 typing 政策，未来 cleanup PR 触动新模块时按需扩展
- 历史 type error 全 repo 扫——按 `feedback_historical_debt_isolation`，不扩 scope

---

## §2 实施策略

### §2.1 M-6 函数级 import → 模块级

**目标位置**：`prewarm_config_lists` 函数体头部两行 `from ... import ...`（main 当前
line 557-558；plan 实施时 grep 重新定位以防漂移）：

```python
def prewarm_config_lists(...):
    if os.environ.get("CAD_SW_BROKER_DISABLE") == "1":
        return
    from adapters.solidworks import sw_config_lists_cache as cache_mod  # 移走
    from adapters.solidworks.sw_detect import detect_solidworks         # 移走
    cache = cache_mod._load_config_lists_cache()
    ...
```

**改为**——把这两行提到文件顶部 import 段（与 `from typing import Any` 等并列）：

```python
# 文件顶部 import 段
from adapters.solidworks import sw_config_lists_cache as cache_mod
from adapters.solidworks.sw_detect import detect_solidworks

def prewarm_config_lists(...):
    if os.environ.get("CAD_SW_BROKER_DISABLE") == "1":
        return
    cache = cache_mod._load_config_lists_cache()
    ...
```

**循环依赖验证**（spec rev 1 写作时执行）：
- `sw_config_lists_cache.py` 不反向 import `sw_config_broker`（grep `from adapters.solidworks.sw_config_broker` 仅 `sw_toolbox_adapter.py` + `gen_std_parts.py` 命中）
- `sw_detect.py` 同样不反向 import

模块级 import 也是 `cad_pipeline.py` 既有 best practice（该文件注释明示
"`mock.patch('cad_pipeline.detect_solidworks')` 需要名字存在于本模块命名空间"）。

### §2.2 M-7 Literal type 替代运行时校验

**Step 1**——在 `sw_config_broker.py` 顶部声明类型别名：

```python
from typing import Literal

InvalidationReason = Literal[
    "bom_dim_signature_changed",
    "sldprt_filename_changed",
    "config_name_not_in_available_configs",
]

# 保留 INVALIDATION_REASONS frozenset 作为运行时枚举集合（log/序列化/审计可用）；
# 删除其在 _move_decision_to_history 头部的强制校验（M-7 决策）。
INVALIDATION_REASONS: frozenset[InvalidationReason] = frozenset({
    "bom_dim_signature_changed",
    "sldprt_filename_changed",
    "config_name_not_in_available_configs",
})
```

**Step 2**——`_validate_cached_decision` 签名改：

```python
def _validate_cached_decision(
    decision: dict[str, Any],
    current_bom_signature: str,
    current_sldprt_filename: str,
    current_available_configs: list[str],
) -> tuple[bool, InvalidationReason | None]:
    ...
```

**Step 3**——`_move_decision_to_history` 签名改 + 删运行时校验：

```python
def _move_decision_to_history(
    envelope: dict[str, Any],
    subsystem: str,
    part_no: str,
    invalidation_reason: InvalidationReason,  # 类型收紧（M-7）
) -> None:
    """..."""
    # ── 删除函数头部 4 行 INVALIDATION_REASONS 运行时校验（main 当前 line 419-423）──
    # mypy strict CI gate 编译期保证 caller 传入 InvalidationReason 字面量。
    decision = envelope["decisions_by_subsystem"][subsystem].pop(part_no)
    envelope.setdefault("decisions_history", []).append({...})
```

**测试影响**：
- 删除：`tests/test_sw_config_broker.py` 中 `TestDecisionAccessors.test_move_decision_rejects_unknown_reason`
  方法（main 当前 line 602）—— 该测试断言 `pytest.raises(ValueError, match="未知 invalidation_reason")`，
  M-7 后此 ValueError 不再 raise（mypy 编译期截获）
- 改写：`_validate_cached_decision` 返回值断言保持不变（运行时仍是 3 字面量字符串之一）

### §2.3 M-8 caller None guard

**目标位置**：`_resolve_config_for_part_unlocked` 函数 cached decision 失效分支
（main 当前 line 812-815；plan 实施时 grep `_move_decision_to_history\(envelope` caller 重新定位）：

```python
else:
    # 失效：先持久化 history（即便后续抛异常，磁盘状态也已收敛）
    _move_decision_to_history(envelope, subsystem, part_no, invalid_reason)
    _save_decisions_envelope(envelope)
```

**改为**：

```python
else:
    # 失效：先持久化 history（即便后续抛异常，磁盘状态也已收敛）
    # _validate_cached_decision 契约：valid=False ⇒ invalid_reason is not None。
    # mypy 无法跨函数推断此契约，显式 assert narrow 类型并锁定不变量。
    assert invalid_reason is not None
    _move_decision_to_history(envelope, subsystem, part_no, invalid_reason)
    _save_decisions_envelope(envelope)
```

**为什么用 `assert` 而非 `if x is None: raise RuntimeError(...)`**：
- mypy 对 `assert` narrow 完全识别（自动收紧 `Literal[...] | None` → `Literal[...]`）
- 本 codebase 不跑 `python -O`（`pyproject.toml` 无相关配置）
- 契约被违反不应进入 try/except 模糊化——assert 失败立即停止，磁盘状态守护

---

## §3 mypy CI gate（渐进式 typing 政策）

### §3.1 mypy 依赖 + 配置

**安装方式**：跟现有 CI 风格一致——CI step 内直接 `pip install mypy>=1.10`，不动
`pyproject.toml [project.optional-dependencies]`（main 当前**无** `dev` 群组，pytest 等
开发依赖也是直接 pip install；为单一 mypy 加 dev 群组属 scope 扩张，违反
`feedback_historical_debt_isolation`）。

**`pyproject.toml` 仅新增 `[tool.mypy]` section**（main 当前无此 section，干净添加）：

```toml
[tool.mypy]
# 渐进式 typing 政策（spec §11 M-7 决策）：仅本 PR 触动模块进 strict。
# 未来 cleanup PR 触动新模块时按需在 [[tool.mypy.overrides]] 加入。
python_version = "3.11"
strict_optional = true
warn_redundant_casts = true
warn_unused_ignores = true
ignore_missing_imports = true  # 默认非 strict 防历史债爆炸

[[tool.mypy.overrides]]
module = "adapters.solidworks.sw_config_broker"
strict = true
```

### §3.2 CI workflow（`.github/workflows/tests.yml` 新增 job）

```yaml
mypy-strict:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: '3.11'
    - run: pip install "mypy>=1.10"
    - run: mypy --platform=win32 adapters/solidworks/sw_config_broker.py
```

**`--platform=win32` 必需**：模块含 `msvcrt`（line 728，函数级 import，Windows-only API）；
mypy 在 ubuntu 跑需告知目标平台。CLI flag 而非 `[tool.mypy] platform = "win32"`——
配置全局 platform 会污染未来其他跨平台模块（`[[overrides]] platform` mypy 不支持）。

### §3.3 渐进扩展政策

未来 follow-up PR 触动新模块时：
1. 仅在 PR 真正修改的模块 `[[tool.mypy.overrides]]` 加入
2. 加入后该模块必须 mypy 全绿（**禁止** `# type: ignore` 或 `disable_error_code`）
3. 不主动扫历史模块加 strict（`feedback_historical_debt_isolation`）

### §3.4 Branch protection（manual post-merge action）

**merge 后必做**（写入 PR description checklist + memory）：
1. GitHub repo settings → branches → main 分支 → required status checks
2. 加入 `mypy-strict` 必过

否则 gate 形同虚设——参考 PR #21 加 `regression` 必过先例。

---

## §4 测试策略

按澄清问题 4 决策（C 粒度）：仅 M-8 加 1 个 assertion 契约测试，M-6/M-7 依赖现有 + mypy CI 守护。

### §4.1 现有测试 inventory（守护范围；main 实测 grep 结果）

```
tests/test_sw_config_broker.py
├─ class TestPrewarmConfigLists                              ← M-6 守护
├─ class TestDecisionAccessors
│  ├─ test_move_decision_to_history                          ← M-7 守护（3 reason 枚举）
│  └─ test_move_decision_rejects_unknown_reason              ← M-7 影响（**需删除**）
├─ class TestValidateCachedDecision                          ← M-7 守护
├─ class TestValidateCachedDecisionRobustness                ← M-7 守护（边界）
└─ class TestResolveConfigForPart                            ← M-8 守护（cached 失效→fall through）
```

行号留给 plan 实施时现场 grep（避免 spec drift）。

### §4.2 M-7 测试删除步骤

执行 M-7 前先 grep 验证：

```bash
grep -n "test_move_decision_rejects_unknown_reason\|未知 invalidation_reason" tests/test_sw_config_broker.py
```

预期匹配 1 个方法定义 + 1 个 `pytest.raises(...match="未知 invalidation_reason")`；
**整段方法删除**（不保留为 mypy compile-time 注释——mypy CI gate 已守护编译期等价语义）。

### §4.3 M-8 新增测试

**新增位置**：`tests/test_sw_config_broker.py`（沿用既有 broker 测试文件，不开新文件）

**测试用例骨架**：

```python
def test_invalid_reason_assertion_holds_under_validate_contract(
    monkeypatch, tmp_project_dir
):
    """M-8 锁定契约：_validate_cached_decision 返回 (False, None) 时
    caller 必抛 AssertionError 而非 silent 写脏 history。

    背景：spec §11 M-8。assert 在 release 部署常被 -O 剥离；本测试守护
    "契约破裂必须显式失败" 的不变量，未来若把 assert 改成 if/raise（用户偏好
    或运维需求），此测试仍能守护行为不变。
    """
    from adapters.solidworks import sw_config_broker

    def _broken_validate(*args, **kwargs):
        return (False, None)  # 契约破裂：valid=False 但 reason=None

    monkeypatch.setattr(
        sw_config_broker, "_validate_cached_decision", _broken_validate
    )

    # 复用 TestRunCachedFallbackToRuleMatch 的 envelope/bom_row fixtures
    # 走到 cached_decision 失效路径
    with pytest.raises(AssertionError):
        sw_config_broker._resolve_config(...)
```

### §4.4 mypy CI 守护范围（M-7 + M-8 通用）

`mypy --platform=win32 adapters/solidworks/sw_config_broker.py` 在 ubuntu CI 跑（strict
通过 §3.1 `[[tool.mypy.overrides]] strict = true` 已生效），**编译期捕获**：
- `_move_decision_to_history` 传入未知字面量（替代 M-7 删的 ValueError）
- `_validate_cached_decision` 返回类型与 caller 用法不匹配（替代 M-8 缺的 None guard）

任何新增 type error → CI fail → PR 阻塞 merge。

### §4.5 覆盖率 gate 影响（PR #21 加的 ≥95%）

| 改动 | 覆盖率影响 |
|---|---|
| M-7 删运行时校验 4 行 | 分母 -4（覆盖率 ↑） |
| M-6 移 import | 不变 |
| M-8 加 assert | 分母 +1，分子 +1（M-8 测试覆盖该 assert）→ 覆盖率几乎不变 |

**净影响**：覆盖率轻微 ↑，无 gate 风险。

### §4.6 测试统计预估

- 删除：1-2 个 `_move_decision_to_history` ValueError 测试（M-7）
- 新增：1 个 M-8 assertion 契约测试
- 修改：0（refactor 行为一致）

**净增 ≈ -1 ~ 0 个用例**，CI 跑时间无感影响。

---

## §5 文档延后处理（M-3 + I-4）

### §5.1 M-3 处理

`sw_config_broker.py:450-453` 注释已充分 trace 设计意图（worker 路径不需要 reload，
与 `_decisions_path` 哲学不同——session 32 决策记录）；M-3 spec 原话"加 reload 测试"
需求由 `tests/conftest.py` 的 `tmp_project_dir` fixture 既有覆盖。

**本 PR 动作**：
- ✅ 在 `2026-04-26-sw-toolbox-config-list-cache-design.md` §11 标 M-3 closed (doc-only)
- ❌ 不改代码、不新加测试

### §5.2 I-4 处理

`_envelope_invalidated` 附近加 1 行注释（具体行号实施时 grep 定位）：

```python
# I-4 已知限制：mtime+size 哈希 collision（SW UI 编辑保留同字节 + 同 mtime）
# 极罕见——SW 改任何 config 都会更新 mtime；不修。
```

spec §11 标 I-4 closed (won't fix)。

### §5.3 spec rev 6（PR #21）§11 联动 edit

`2026-04-26-sw-toolbox-config-list-cache-design.md` 在 main 已存在（PR #19 创建），
PR #21 与本 PR 都只 edit 其 §11 区域。merge 顺序前置条件：**PR #21 必须先 merge 进 main**，
否则两 PR 同 section edit 会触发合并冲突。

implementation plan 必须包含此前置条件检查（plan task：`pre-check: PR #21 已 merge`）。

### §5.4 spec §11 整体清单（merge 后）

```
### 已修
- C-1 / I-1 (PR #19) ✅
- I-2 / I-3 (PR #20) ✅
- M-2 / M-4 (PR #21) ✅
- M-3 / M-6 / M-7 / M-8 / I-4 (本 PR) ✅

### 仍 open（3 项）
- M-1 fsync 缺失（独立 PR）
- M-5 prewarm timeout 缩放（独立 PR）
- M-9 CI gate trace（纯文档已注释化，开放跟踪不丢线索）
```

---

## §6 工作流

### §6.1 Branch 命名

`feat/sw-config-broker-followup-cleanup`（已 cut off main，spec rev 1 写作时）

### §6.2 Commit 切分

按"单一主题、可回滚"切 6 个 commit：

```
1. test(sw_config_broker): RED — M-8 assertion 契约测试（先 fail）
2. feat(sw_config_broker): M-7 + M-8 — Literal type + caller assert
3. chore(sw_config_broker): M-6 — 函数级 import 提到模块级
4. ci(mypy): mypy strict gate (sw_config_broker.py only)
5. docs(spec): §11 标 M-3/M-6/M-7/M-8/I-4 closed + 引用本 spec
6. chore(sw_config_broker): I-4 加 1 行已知限制注释
```

Step 1 严格按 CLAUDE.md TDD 铁律先 fail：commit 1 阶段 `_resolve_config` 还未加
`assert`，mock 契约破裂时不抛 AssertionError，测试 RED。commit 2 加 assert 后 GREEN。

### §6.3 CHANGELOG.md 条目

```markdown
## [v2.21.1] - 2026-04-27

### Changed
- **sw_config_broker §11 minor cleanup（5 项 closed）**：
  - M-6: 函数级 import (`detect_solidworks` / `sw_config_lists_cache`) 提到模块级
  - M-7: `_validate_cached_decision` 返回类型用 `Literal[...]` 替代 `str`，
    删除 `_move_decision_to_history` 头部运行时校验（mypy 编译期保证）
  - M-8: cached decision 失效路径加 `assert invalid_reason is not None` 锁定契约
  - M-3 / I-4: 文档化 won't-fix（详见 spec §11）

### Added
- **mypy strict CI gate（渐进式 typing 政策）**：仅
  `adapters/solidworks/sw_config_broker.py` 进 strict 检查（`pyproject.toml [tool.mypy]`
  + `tests.yml mypy-strict job`）。未来 cleanup PR 触动新模块时按需扩展。
  CI step 直接 `pip install "mypy>=1.10"`（main pyproject 无 `dev` 群组，本 PR 不引入）。
```

### §6.4 PR description 模板

```markdown
## Summary
- §11 follow-up cleanup: M-6/M-7/M-8 真改 + M-3/I-4 文档化
- mypy strict CI gate scope = sw_config_broker.py 一文件（渐进式 typing）
- spec §11 close 5 项 → 仍 open 3 项（M-1 / M-5 / M-9）

## Test plan
- [ ] 既有 broker 测试 199+ PASS 不 regression
- [ ] M-8 新增契约测试 PASS
- [ ] mypy strict gate ubuntu CI 绿
- [ ] 覆盖率 gate 仍 ≥95%（Linux/Windows）
- [ ] 手动校验：broker prewarm 路径走通（依赖本机 SW 2024 Premium）

## Post-merge actions
- [ ] Branch protection 加 `mypy-strict` 进 main 必过 checks
- [ ] tag v2.21.1 + GitHub Release notes
- [ ] memory: `project_current_status.md` 更新 §11 closed 进度
```

### §6.5 前置条件

**本 PR merge 前**：PR #21（v2.21.0）必须先 merge 进 main——否则 §5.3 的 spec rev 6
edit 会因 base file 不存在 fail。plan 第一个 task 必为 `pre-check: PR #21 merged`。

---

## §7 风险评估 + 不变量

### §7.1 风险

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| M-7 测试删除遗漏（仅 1 方法 `test_move_decision_rejects_unknown_reason`） | 低 | mypy CI fail | §4.2 已锁定方法名，grep 验证 1 命中 |
| mypy `--platform=win32` 在 ubuntu 上仍误报 stub 缺失 | 低 | CI fail | 实施时 hot-loop 调，必要时 mypy `>=1.11` |
| PR #21 与本 PR §11 区域并行 edit 冲突 | 中 | merge conflict | plan pre-check 强制 PR #21 先 merge |
| 覆盖率 gate 误算（M-7 删行 vs M-8 加 assert 抵消计算错） | 低 | CI fail | local pytest --cov 实测前置 |
| msvcrt-only 函数 mypy strict 仍判 unreachable | 低 | CI fail | `if TYPE_CHECKING:` import 兜底 |

### §7.2 不变量（行为契约）

本 PR 必须保持以下不变量（refactor 性质 = 行为不变）：

1. `_validate_cached_decision` 仍返回 3 字面量字符串之一（valid=False 时）或 None（valid=True 时）
2. `_move_decision_to_history` 仍把 decision 拷贝到 history + 删除原位
3. cached decision 失效路径仍持久化 history 后 fall through 规则匹配
4. `prewarm_config_lists` 行为不变（M-6 纯结构调整）
5. `INVALIDATION_REASONS` frozenset 仍可被外部 import（log/序列化用例）

---

## §8 完成定义（Definition of Done）

- [ ] PR #21 已 merge 进 main（前置条件）
- [ ] 6 个 commit 按 §6.2 顺序提交（含 RED 测试 commit 1）
- [ ] 既有 199+ broker 测试全 PASS
- [ ] M-8 新增 1 测试 PASS
- [ ] M-7 删除 1-2 ValueError 测试，无遗漏
- [ ] `mypy --platform=win32 --strict adapters/solidworks/sw_config_broker.py` 退出码 0
- [ ] CI matrix 6 平台 × py 版本全绿 + `regression` job 绿 + 新 `mypy-strict` job 绿
- [ ] 覆盖率 gate ≥95%（Linux + Windows）
- [ ] CHANGELOG.md 加 v2.21.1 条目
- [ ] PR description 写完 + ready-for-review
- [ ] PR #21 spec §11 标 5 项 closed 引用本 spec

---

## §9 引用

- 前置 PR：[2026-04-27-sw-config-broker-m2-m4-cleanup-design.md](2026-04-27-sw-config-broker-m2-m4-cleanup-design.md)（M-2/M-4 closed）
- §11 源头：[2026-04-26-sw-toolbox-config-list-cache-design.md §11](2026-04-26-sw-toolbox-config-list-cache-design.md)（PR #19 self-review 登记 7 follow-up）
- I-2 + I-3 closure：[2026-04-26-sw-config-broker-i2-i3-fix-design.md](2026-04-26-sw-config-broker-i2-i3-fix-design.md)（PR #20）
- 北极星：memory `project_north_star.md`
- 历史债隔离：memory `feedback_historical_debt_isolation.md`
- CI gate platform split：memory `feedback_ci_cov_gate_platform_split.md`

---

## §10 maintainer note

- mypy strict scope 扩展规则严格按 §3.3 渐进式政策——**禁止**为绕过本 PR 范围而扫历史模块加 strict
- M-7 删除 INVALIDATION_REASONS 运行时校验是有意决策（YAGNI + 类型系统已守）；未来若有人想"加回防御校验"，须先 grep 调用方已加新 caller，否则保持删除状态
- M-8 用 `assert` 是 mypy narrow 策略；如未来项目跑 `python -O` 部署，须升级为 `if invalid_reason is None: raise RuntimeError(...)`，并保留 §4.3 测试

---

## §11 自身 follow-up 占位

PR 创建后 self-review 与 user-review 发现的新问题登记此节，按 Critical / Important / Minor
分级，类比 `2026-04-26-sw-toolbox-config-list-cache-design.md` §11 模式。

### §11.1 PR Review followup（占位）

（rev 1 阶段无内容；PR 开 review 后回填）
