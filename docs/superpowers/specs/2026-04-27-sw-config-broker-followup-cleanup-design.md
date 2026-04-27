# sw_config_broker §11 follow-up cleanup（M-3/M-6/M-7/M-8/I-4 收官）设计 spec

- 版本：rev 1
- 创建：2026-04-27
- 模块：`adapters/solidworks/sw_config_broker.py`（含上下游 spec 与 CI 配置）
- 目标 PR：v2.21.1（patch）
- 前置 PR：[v2.21.0 (PR #21) M-2/M-4 cleanup](2026-04-27-sw-config-broker-m2-m4-cleanup-design.md)（forward link：该文件由 PR #21 创建，main merge 后路径稳定生效）
- 类型：§11 follow-up cleanup

---

## §1 背景 + 范围

PR #21（v2.21.0）关闭 §11 中 M-2 / M-4 + 新登记 M-8 / M-9 后，
`2026-04-26-sw-toolbox-config-list-cache-design.md` §11 状态：

- **open 7 项**（需修复）：M-1 / M-3 / M-5 / M-6 / M-7 / M-8 / I-4
- **doc-only tracking 1 项**：M-9（CI gate trace 已在 PR #21 spec 注释化，无需修复，仅
  保留跟踪不丢线索）

本 PR 收官 open 中 5 项（**M-3 / M-6 / M-7 / M-8 / I-4**），剩 open 2 项（M-1 fsync /
M-5 timeout 公式）涉及真持久化语义改动 + 真行为基线重测，推迟到独立 PR。M-9 状态
不变（doc-only tracking）。

### §1.1 范围分类

| 类型 | 项 | 说明 |
|---|---|---|
| 真改代码 | M-6 | 函数级 import → 模块级（`detect_solidworks` + `sw_config_lists_cache`） |
| 真改代码 | M-7 | `_validate_cached_decision` 返回类型用 `Literal[...]` 替代 `str`，删除 `_move_decision_to_history` 头部运行时校验 |
| 真改代码 | M-8 | cached decision 失效路径加 `assert invalid_reason is not None`（caller 侧 None guard） |
| CI 新增 | — | mypy strict gate，scope 仅 `adapters/solidworks/sw_config_broker.py`（渐进式 typing 政策） |
| 文档化 | M-3 | `_PROJECT_ROOT_FOR_WORKER` 模块级 vs 函数级 import 不对称——`sw_config_broker.py` 该常量上方注释已充分 trace，**零代码改动** |
| 文档化 | I-4 | mtime+size collision 极罕见——在 **`sw_config_lists_cache.py`** `_envelope_invalidated`（定义处）附近加 1 行已知限制注释 |

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

**Step 4**（M-7 IO 边界守护）——`_load_decisions_envelope` 加读取端 runtime 校验：

```python
def _load_decisions_envelope() -> dict[str, Any]:
    envelope = json.load(...)  # 现有 IO 逻辑

    # M-7 IO 边界守护（spec §7.2 invariant 1 强语义）：
    # 跨 IO 边界反序列化的 decisions_history[*].invalidation_reason 可能含
    # 旧 schema 字符串（PR #19 之前 / 用户手编 / 外部源），mypy 编译期 Literal
    # 守护对 IO 边界外不生效，读取端 runtime 校验补强。
    for entry in envelope.get("decisions_history", []):
        if entry.get("invalidation_reason") not in INVALIDATION_REASONS:
            raise ValueError(
                f"decisions_history 含未知 invalidation_reason: "
                f"{entry.get('invalidation_reason')!r}（schema 损坏或老版本数据）"
            )
    return envelope
```

**设计配对**：
- 写入端（`_move_decision_to_history`）：caller 已被 mypy `Literal` 守护，删运行时校验
- 读取端（`_load_decisions_envelope`）：JSON 反序列化结果跨 IO 边界，加 runtime 校验
- 净改动：写入端 -1 处校验 + 读取端 +1 处校验，跨 IO 边界守护完整

**测试影响**：
- 删除：`tests/test_sw_config_broker.py` 中 `TestDecisionAccessors.test_move_decision_rejects_unknown_reason`
  方法（main 当前 line 602）—— 该测试断言 `pytest.raises(ValueError, match="未知 invalidation_reason")`，
  M-7 写入端删校验后此 ValueError 不再从写入端 raise（mypy 编译期截获）
- 新增：`TestDecisionsEnvelopeIO.test_load_rejects_unknown_invalidation_reason_in_history`
  方法 —— 守护 IO 边界 runtime 校验（构造老 envelope JSON 含 `"bom_change"` 等历史
  字符串 → `_load_decisions_envelope` 必抛 `ValueError` match `"schema 损坏或老版本数据"`）
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
python_version = "3.10"  # 与 pyproject.toml `requires-python = ">=3.10"` 对齐，
                          # 让 mypy 检查 3.10 不支持的语法（如 PEP 695 type alias）
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
    - uses: actions/checkout@v6  # 与现有 tests.yml 既有 jobs 版本对齐
    - uses: actions/setup-python@v6
      with:
        python-version: '3.11'
    - run: pip install "mypy>=1.10"
    - run: mypy --platform=win32 adapters/solidworks/sw_config_broker.py
```

**`--platform=win32` 必需**：模块含 `msvcrt`（`_project_file_lock` 函数体内函数级 import，
Windows-only API；plan 实施时 grep `import msvcrt` 现场定位）；mypy 在 ubuntu 跑需告知
目标平台。CLI flag 而非 `[tool.mypy] platform = "win32"`——配置全局 platform 会污染未来
其他跨平台模块（`[[overrides]] platform` mypy 不支持）。

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

## §4 测试策略（详尽版）

按用户 Round 4 反馈"测试越详尽越好"——粒度从 C 升级为 **A+ 全维度详尽**：每条
§7.2 invariant 必有显式守护测试；每个改动路径必有 happy + boundary + error 三类
覆盖；mypy CI gate 自校验防 gate 配置漂移。

### §4.1 测试覆盖原则

1. **invariant 反向 trace**：每个新测试在 docstring 引用守护的 spec § 节号 / invariant
   编号——防 spec 演进时测试与意图脱节
2. **fixture isolation**：用 `tmp_project_dir` / `monkeypatch` 不依赖外部状态，独立可重现
3. **assertion message 详尽**：失败时直接定位破坏的 invariant，引用 spec §7.2 编号
4. **参数化优先**：用 `pytest.parametrize` 覆盖多场景，避免复制粘贴
5. **mock vs 真实合理选择**：边界守护用 mock（可重现），端到端用真实 IO（fixture 文件）
6. **三类路径**：每个改动覆盖 happy path + boundary（边界值）+ error path（异常路径）

### §4.2 测试矩阵概览（5 类 20 新测试 + 1 删除）

```
M-6 模块级 import        →  4 测试（T1-T4）  → §4.3
M-7 写入端 + Literal 类型 →  3 测试 + 1 删除（T5-T7） → §4.4
M-7 IO 边界守护           →  5 测试（T8-T12） → §4.5
M-8 caller assert         →  4 测试（T13-T16） → §4.6
mypy CI gate 自校验       →  2 测试（T17-T18） → §4.7
集成 + invariant 回归     →  2 测试（T19-T20） → §4.8
```

**净增 = +19 个用例**（-1 删 + 20 新加）。CI 跑时间影响：每测试 <100ms × 20 ≈ 2 秒，无感。

### §4.3 M-6 模块级 import 测试（4 测试，T1-T4）

| # | 测试 | 守护 invariant |
|---|---|---|
| **T1** | `test_detect_solidworks_module_level_attribute` | 模块级名字暴露：`hasattr(sw_config_broker, 'detect_solidworks')` ⇒ True |
| **T2** | `test_cache_mod_module_level_attribute` | `hasattr(sw_config_broker, 'cache_mod')` ⇒ True（M-6 第二个 import） |
| **T3** | `test_module_level_import_patchable` | `mock.patch.object(sw_config_broker, 'detect_solidworks')` 在 prewarm 路径生效（cad_pipeline.py 既有 best practice 模式） |
| **T4** | `test_no_circular_import_on_reload` | `importlib.reload(sw_config_broker)` 不抛 ImportError —— 反向防 sw_config_lists_cache / sw_detect 未来加 broker import |

**测试 class 位置**：新增 `class TestModuleLevelImports`（沿用 `tests/test_sw_config_broker.py`）

### §4.4 M-7 写入端 + Literal 类型测试（3 新增 T5-T7 + 1 删除）

**删除**：`TestDecisionAccessors.test_move_decision_rejects_unknown_reason`（§4.2 之前
版本已锁定，此 PR 删——M-7 写入端校验删除后 ValueError 不再 raise）

| # | 测试 | 守护 invariant |
|---|---|---|
| **T5** | `test_validate_returns_typed_literal_or_none` | §7.2 invariant 1 写入端：`_validate_cached_decision` 返回 tuple 第二位运行时是 3 字面量字符串之一（valid=False）或 None（valid=True）—— 参数化 4 个 case（3 reason + 1 None） |
| **T6** | `test_invalidation_reasons_frozenset_immutable_and_complete` | `INVALIDATION_REASONS` 包含且仅包含 3 个 Literal 字面量，`isinstance(_, frozenset)` 且不可变（`pytest.raises(AttributeError)` on `_.add()`）—— 防御未来误删/误改 |
| **T7** | `test_move_decision_each_reason_appends_history_correctly` | `_move_decision_to_history` 对 3 reason 各自参数化执行 → `decisions_history[-1]['invalidation_reason']` 等于传入值，`decisions_by_subsystem[...].pop()` 真删除 |

**测试位置**：T5/T6 沿用 `class TestValidateCachedDecision` + 新加 invariant 测试；
T7 改写 `class TestDecisionAccessors.test_move_decision_to_history`（参数化扩展）

### §4.5 M-7 IO 边界守护测试（5 测试，T8-T12）

每个测试构造特定损坏 envelope JSON，验证 `_load_decisions_envelope` 必抛 `ValueError`
match `"schema 损坏或老版本数据"`：

| # | 测试 | 边界场景 |
|---|---|---|
| **T8** | `test_load_rejects_unknown_string_in_history` | `decisions_history[0].invalidation_reason == "bom_change"`（PR #19 之前命名）|
| **T9** | `test_load_rejects_none_invalidation_reason` | `invalidation_reason == None`（字段存在但值 null） |
| **T10** | `test_load_rejects_empty_string_invalidation_reason` | `invalidation_reason == ""`（空串） |
| **T11** | `test_load_rejects_int_invalidation_reason` | `invalidation_reason == 0`（用户手编混入数字） |
| **T12** | `test_load_rejects_partial_corrupted_history` | 多条 history（5 条），其中 1 条含未知 reason，其他 4 条合法 → 整体 raise（不 silent skip） |

**测试 class 位置**：沿用 `class TestDecisionsEnvelopeIO`（main 已存在）

**fixture 模式**：每测试构造 minimal valid envelope dict + 注入坏字段 → `json.dump`
到 `tmp_project_dir / decisions.json` → 调 `_load_decisions_envelope` → `pytest.raises`

### §4.6 M-8 caller assert + 路径覆盖测试（4 测试，T13-T16）

| # | 测试 | 守护点 |
|---|---|---|
| **T13** | `test_assertion_holds_under_broken_validate_contract` | mock `_validate_cached_decision` 返回 `(False, None)` → caller 必抛 `AssertionError`（核心契约守护，§2.3） |
| **T14** | `test_assertion_error_message_includes_contract_reference` | T13 升级版：抛 AssertionError 时 message 含 spec §7.2 invariant 引用（如 `"_validate_cached_decision contract"`） |
| **T15** | `test_cached_invalid_with_each_reason_triggers_history_append` | 参数化 3 reason，每个走 cached invalidate 端到端：构造 envelope cached + 触发 invalidation → 验证 `decisions_history` 实际 append 对应 reason，`decisions_by_subsystem` pop 原 entry |
| **T16** | `test_cached_valid_does_not_trigger_assert` | 防御性：valid=True + invalid_reason=None 路径不触发 assert，正常返回 ConfigResolution |

**测试 class 位置**：T13-T14 新增 `class TestM8ContractGuard`；T15 参数化扩展
`class TestResolveConfigForPart`；T16 加入既有 cached path 测试

### §4.7 mypy CI gate 自校验测试（2 测试，T17-T18）

防御 mypy CI 配置漂移（如 reviewer 误改 `[[overrides]] strict = true` 为 false 或
exclude sw_config_broker.py）：

| # | 测试 | 守护点 |
|---|---|---|
| **T17** | `test_mypy_strict_catches_invalid_literal_assignment` | subprocess 调 `mypy --platform=win32 tests/fixtures/_mypy_invalid_literal_fixture.py` → 必 fail with non-zero exit code（fixture 文件内含故意类型错的 `_move_decision_to_history(envelope, "es", "p", "bom_change")` 字面量传错） |
| **T18** | `test_mypy_strict_passes_current_module` | subprocess 调 `mypy --platform=win32 adapters/solidworks/sw_config_broker.py` → 退出码 0（守护"当前模块永远 mypy 全绿"，作 CI gate 实施时 baseline 验证） |

**测试 class 位置**：新增 `class TestMypyCIGate`

**fixture 文件**：`tests/fixtures/_mypy_invalid_literal_fixture.py`（PR 同 commit 加）

**marker**：`@pytest.mark.mypy`（独立 marker 让本地默认跑过滤掉 subprocess 测试，
CI 显式跑全部）

### §4.8 集成 + invariant 回归测试（2 测试，T19-T20）

| # | 测试 | 守护点 |
|---|---|---|
| **T19** | `test_e2e_prewarm_resolve_invalidate_history_pipeline` | 端到端链路：mock SW worker → prewarm 4 件 → resolve 触发 cached invalidate → fall through 规则匹配 → 验证 history append 正确 + envelope 状态收敛 |
| **T20** | `test_section_7_2_invariants_are_preserved` | §7.2 5 条 invariant 参数化逐条 sub-assertion：每条 invariant 一个 `subTest` 块，docstring 引用 §7.2 第 N 条，break 任何一条立即 fail |

**测试 class 位置**：T19 沿用 `class TestPrewarmConfigLists` 或新增 `class TestE2EPipeline`；
T20 新增 `class TestSection72InvariantsRegression`

### §4.9 覆盖率 gate 影响（PR #21 加的 ≥95%）

| 改动 | statement 影响 | 测试覆盖 |
|---|---|---|
| M-7 写入端删校验 | 分母 -2 statement（1 if + 1 raise） | T5/T6/T7（直接覆盖剩余 _move 路径） |
| M-7 读取端加 IO 校验 | 分母 +4 statement（for + if + raise + get 链） | T8-T12（5 测试覆盖） |
| M-6 import 移位 | 不变（模块级 import 不计 statement） | T1-T4（直接覆盖新位置） |
| M-8 caller assert | 分母 +1 statement | T13/T14/T15（多角度覆盖） |
| I-4 注释 | 不变（注释不计 statement） | — |

**净影响**：分母 +3（写入 -2 + 读取 +4 + assert +1），分子 +5+（新测试全覆盖新增 statement）；
覆盖率轻微 ↑。具体 statement 数 plan 实施时 `pytest --cov` 实测确认（plan 第 0 task）。

### §4.10 测试统计

- **删除**：1 个测试方法（`test_move_decision_rejects_unknown_reason`）
- **新增**：20 个测试（T1-T20，按 §4.3-§4.8 分类）
- **修改**：1 个测试参数化扩展（`test_move_decision_to_history` → T7 多 reason）
- **新增 fixture 文件**：1 个（`tests/fixtures/_mypy_invalid_literal_fixture.py` 给 T17）
- **新增测试 class**：4 个（`TestModuleLevelImports` / `TestM8ContractGuard` /
  `TestMypyCIGate` / `TestSection72InvariantsRegression`）

**净增 = +19 个用例**，CI 跑时间影响 ≈ 2 秒（subprocess mypy 测试 T17/T18 各约 0.5-1
秒，其余 <100ms）。

---

## §5 文档延后处理（M-3 + I-4）

### §5.1 M-3 处理

`sw_config_broker.py` 中 `_PROJECT_ROOT_FOR_WORKER` 常量上方的注释（说明"worker 路径
不需要 reload，与 `_decisions_path` 哲学不同——session 32 决策记录"）已充分 trace
设计意图；M-3 spec 原话"加 reload 测试"需求由 `tests/conftest.py` 的 `tmp_project_dir`
fixture 既有覆盖（行号 plan 实施时现场 grep）。

**本 PR 动作**：
- ✅ 在 `2026-04-26-sw-toolbox-config-list-cache-design.md` §11 标 M-3 closed (doc-only)
- ❌ 不改代码、不新加测试

### §5.2 I-4 处理

**目标文件**：`adapters/solidworks/sw_config_lists_cache.py`（`_envelope_invalidated`
**定义处**——main grep 显示该函数定义在此文件 line 101，broker 只是 caller）。
具体行号 plan 实施时 grep 定位。

```python
# I-4 已知限制：mtime+size 哈希 collision（SW UI 编辑保留同字节 + 同 mtime）
# 极罕见——SW 改任何 config 都会更新 mtime；不修。
```

spec §11 标 I-4 closed (won't fix)。

### §5.3 PR #19 spec §11 联动 edit

§11 follow-up 列表的源头是 PR #19 创建的 `2026-04-26-sw-toolbox-config-list-cache-design.md`
（main 已存在）。后续每个 cleanup PR（PR #20 / PR #21 / 本 PR）都在该文件 §11 标对应项 closed。

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

### 仍 open（2 项）
- M-1 fsync 缺失（独立 PR）
- M-5 prewarm timeout 缩放（独立 PR）

### doc-only tracking（1 项）
- M-9 CI gate trace（纯文档已注释化，保留跟踪不丢线索）
```

---

## §6 工作流

### §6.1 Branch 命名

`feat/sw-config-broker-followup-cleanup`（已 cut off main，spec rev 1 写作时）

### §6.2 Commit 切分

按"单一主题、可回滚 + TDD 严格 + 测试详尽"切 **13 个 commit**。**三原则**：

1. **TDD 严格**：每个新 feature 先 RED 测试 commit → 后 GREEN 实现 commit
2. **测试详尽**：每类测试（M-6/M-7/M-7-IO/M-8/CI gate/集成）独立 commit，主题清晰
3. **spec §11 closure mark（最后 commit）**——避免回滚代码后 spec 仍声明 closed

```
 1. test(sw_config_broker): RED — M-8 caller assert 契约测试套（T13-T16，4 测试）
 2. feat(sw_config_broker): M-8 — caller assert (commit 1 测试 GREEN)
 3. test(sw_config_broker): RED — M-7 IO 边界守护测试套（T8-T12，5 测试）
 4. feat(sw_config_broker): M-7 IO 边界 — _load_decisions_envelope 加读取端校验
    (commit 3 GREEN)
 5. test(sw_config_broker): M-7 写入端 + Literal 类型守护测试（T5-T7，3 测试）
 6. refactor(sw_config_broker): M-7 — Literal type + 写入端删 _move 校验 +
    删 test_move_decision_rejects_unknown_reason
 7. test(sw_config_broker): M-6 模块级 import 守护测试（T1-T4，4 测试）
 8. refactor(sw_config_broker): M-6 — 函数级 import 提到模块级
 9. test(ci): mypy CI gate 反例自校验测试（T17，含 fixture 文件）
10. ci(mypy): mypy strict gate (pyproject.toml + tests.yml mypy-strict job + T18)
11. test(integration): 集成 + §7.2 invariant 回归测试（T19-T20，2 测试）
12. chore(sw_config_lists_cache): I-4 加 1 行已知限制注释
13. docs(spec): §11 标 M-3/M-6/M-7/M-8/I-4 closed + 引用本 spec
```

每个 commit 主题清晰、可独立 review：

- **commit 1-2**：M-8 caller assert，TDD RED→GREEN（4 测试 → assert 实现）
- **commit 3-4**：M-7 IO 边界（H1=A 决策的 new feature），TDD RED→GREEN（5 边界测试 → IO 校验）
- **commit 5-6**：M-7 写入端 refactor —— commit 5 加 3 守护测试（T5-T7）→ commit 6 真正
  refactor，reviewer 焦点 = "写入端可以删 OK，因为 mypy 编译期 + 读取端 runtime + T5-T7 守护"
- **commit 7-8**：M-6 import 移位 —— commit 7 加 4 行为守护测试（T1-T4）→ commit 8 真正移位
- **commit 9-10**：mypy CI gate —— commit 9 加 fixture + 反例测试（T17）→ commit 10 加
  pyproject.toml + tests.yml mypy job + 当前模块自检测试（T18）
- **commit 11**：集成 + invariant 回归（T19-T20）—— 最后兜底
- **commit 12-13**：I-4 注释 / spec §11 closure mark

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
  `adapters/solidworks/sw_config_broker.py` 进 strict 检查
  （`pyproject.toml [tool.mypy] + [[tool.mypy.overrides]]` 两个 section，strict 在
  overrides 内启用）+ `tests.yml mypy-strict job`。未来 cleanup PR 触动新模块时按需扩展。
  CI step 直接 `pip install "mypy>=1.10"`（main pyproject 无 `dev` 群组，本 PR 不引入）。
```

### §6.4 PR description 模板

```markdown
## Summary
- §11 follow-up cleanup: M-6/M-7/M-8 真改 + M-3/I-4 文档化
- mypy strict CI gate scope = sw_config_broker.py 一文件（渐进式 typing）
- spec §11 close 5 项 → 仍 open 2 项（M-1 / M-5）+ 1 doc-only tracking（M-9）

## Test plan
- [ ] 既有 broker 测试全 PASS 不 regression（基线数：PR #21 merge 后 main 上 ~199 个，main 当前 108 个；实施时以前置条件 PR #21 merge 后状态为准）
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
| mypy 对函数级 `import msvcrt` 在 `sys.platform != "win32"` early return 后判 unreachable | 低 | CI fail | mypy `--platform=win32` 已让 sys.platform=='win32' 分支 reachable；如仍误报，方案备选：(a) 在 `[[overrides]]` 显式声明该函数 `disable_error_code = ["unreachable"]`（违反 §3.3 但单点特批可文档化）；(b) 重构 msvcrt 操作进单独 helper 函数 |

### §7.2 不变量（行为契约 + 反向 trace 守护测试）

本 PR 必须保持以下 5 条不变量（refactor 性质 = 行为不变）。每条标对应守护测试编号
（T1-T20，详见 §4）：

1. `_validate_cached_decision` 返回值 tuple 第二位仍是 3 字面量字符串之一（valid=False 时）
   或 None（valid=True 时）；**双层守护**：写入端 mypy 编译期 `Literal` + 读取端
   `_load_decisions_envelope` runtime 校验（spec §2.2 Step 4），跨 IO 边界守护完整
   - 守护测试：**T5**（参数化 4 case）、**T8-T12**（IO 边界 5 case）、**T20**（invariant 回归）
2. `_move_decision_to_history` 仍把 decision 拷贝到 history + 删除原位
   - 守护测试：**T7**（参数化 3 reason）、**T15**（端到端 cached invalidate）、**T20**
3. cached decision 失效路径仍持久化 history 后 fall through 规则匹配
   - 守护测试：**T15**、**T19**（端到端 pipeline）、**T20**
4. `prewarm_config_lists` 行为不变（M-6 纯结构调整）
   - 守护测试：**T1-T4**（模块级 import 行为）、**T19**、**T20**
5. `INVALIDATION_REASONS` frozenset 保留为模块级常量（**当前无外部 caller**——grep 验证仅
   `sw_config_broker.py` 内部定义 + 删除前的运行时校验引用 + 1 个待删测试方法引用）；
   保留意图：未来外部需要 import 时无需修改本模块。如未来确认无任何外部需求，可在后续
   cleanup PR 一并删除常量本身。
   - 守护测试：**T6**（不可变 + 完整性）、**T20**

---

## §8 完成定义（Definition of Done）

- [ ] PR #21 已 merge 进 main（前置条件）
- [ ] 13 个 commit 按 §6.2 顺序提交（含 2 对 RED→GREEN：M-8 commit 1-2 + IO 边界 commit 3-4）
- [ ] 既有 broker 测试全 PASS（基线 ~199，前置条件 PR #21 merge 后）
- [ ] T1-T20 共 20 个新测试全 PASS（净增 +19；参数化测试展开后实际 collect 数更多）
- [ ] 删除 1 个测试方法 `test_move_decision_rejects_unknown_reason`（M-7 写入端校验删）
- [ ] 4 个新测试 class（`TestModuleLevelImports` / `TestM8ContractGuard` / `TestMypyCIGate`
      / `TestSection72InvariantsRegression`）全 PASS
- [ ] §7.2 5 条 invariant 反向 trace 测试（T20）全 PASS
- [ ] M-7 删除 1 个测试方法（commit 6 内）+ 新增 fixture 文件（commit 9 内）+ 新增 4 测试 class，无遗漏
- [ ] `mypy --platform=win32 adapters/solidworks/sw_config_broker.py` 退出码 0
      （strict 通过 §3.1 `[[overrides]] strict = true` 已生效）
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
- M-8 用 `assert` 是 mypy narrow 策略；如未来项目跑 `python -O` 部署，须升级为
  `if invalid_reason is None: raise RuntimeError(...)`，并把 §4.3 测试中
  `pytest.raises(AssertionError)` 同步改为 `pytest.raises(RuntimeError)`（核心契约
  "契约破裂必须显式失败"语义不变；仅断言异常类型变更）

---

## §11 自身 follow-up 占位

PR 创建后 self-review 与 user-review 发现的新问题登记此节，按 Critical / Important / Minor
分级，类比 `2026-04-26-sw-toolbox-config-list-cache-design.md` §11 模式。

### §11.1 PR Review followup（占位）

（rev 1 阶段无内容；PR 开 review 后回填）
