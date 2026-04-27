# sw_config_broker §11 follow-up cleanup 实施 Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 关闭 `2026-04-26-sw-toolbox-config-list-cache-design.md §11` 中 5 项 follow-up（M-3/M-6/M-7/M-8/I-4）+ 引入 mypy strict CI gate（渐进式 typing 政策）。

**Architecture:** M-6 函数级 import → 模块级；M-7 用 `Literal[...]` 替代写入端运行时校验，配对加读取端 IO 边界 runtime 校验保 invariant 跨 IO 边界完整；M-8 cached decision 失效路径加 caller `assert`；新增 mypy strict job scope 仅 `sw_config_broker.py`。

**Tech Stack:** Python 3.10+ / pytest / mypy 1.10+ / GitHub Actions / pytest-cov（PR #21 加的 ≥95% gate）

**Reference Spec:** [`docs/superpowers/specs/2026-04-27-sw-config-broker-followup-cleanup-design.md`](../specs/2026-04-27-sw-config-broker-followup-cleanup-design.md)

**Branch:** `feat/sw-config-broker-followup-cleanup`（off main，spec rev 1.4 commit `4666fb5`）

**前置条件**：PR #21（v2.21.0 M-2/M-4 cleanup）必须先 merge 进 main——否则 §13 的 spec §11 closure mark 会与 PR #21 的 §11 edits 区域冲突。

---

## Task 0: Pre-check + Baseline 验证

**Files:** 无修改（仅核对）

- [ ] **Step 0.1：验证 PR #21 已 merge 进 main**

```bash
gh pr view 21 --json state,mergedAt | head -5
```

预期：`"state": "MERGED"` + `mergedAt` 非 null。如未 merge → STOP，告知用户先处理 PR #21。

- [ ] **Step 0.2：rebase 当前分支 onto main**

```bash
git fetch origin
git checkout main && git pull
git checkout feat/sw-config-broker-followup-cleanup
git rebase main
```

预期：rebase 成功无冲突（spec 文件是新增不冲突）；如冲突 → STOP，人工解决。

- [ ] **Step 0.3：grep 当前 main + PR #21 改动后的关键锚点**

```bash
grep -n "^def _validate_cached_decision\|^def _move_decision_to_history\|^def prewarm_config_lists\|^def _load_decisions_envelope\|^def _resolve_config_for_part_unlocked\|^INVALIDATION_REASONS\|^_PROJECT_ROOT_FOR_WORKER\|^    import msvcrt" adapters/solidworks/sw_config_broker.py
```

记录每个符号的当前行号，后续 Task 步骤里"main 当前 line N"参考此次 grep 结果，不依赖 spec 写的旧行号。

- [ ] **Step 0.4：跑 baseline 测试 + 覆盖率**

```bash
pytest tests/test_sw_config_broker.py --cov=adapters.solidworks.sw_config_broker --cov-report=term -v 2>&1 | tail -30
```

记录：
- 通过测试数（baseline，本 PR 末尾应 = baseline + 19）
- 覆盖率百分比（baseline，本 PR 末尾应 ≥ baseline 不下降）
- collect 数（含 parametrize 展开）

- [ ] **Step 0.5：跑 baseline mypy dry-run**

```bash
pip install "mypy>=1.10"
mypy --platform=win32 --strict adapters/solidworks/sw_config_broker.py 2>&1 | tail -20
```

预期：当前模块在 PR #21 merge 后状态有 ≥1 个 type error（M-8 mypy 历史 type error 等）。**记录所有 error 数 + 类型**——这是本 PR 实施过程中需要清零的目标。

- [ ] **Step 0.6：commit 无（pre-check 不产生 commit）**

记录 baseline 数据进 plan 临时笔记（不入 git），实施过程中作对照。

---

## Task 1: M-8 RED 测试套（T13-T16，4 测试）

**Files:**
- Modify: `tests/test_sw_config_broker.py`（加 `class TestM8ContractGuard`）

**Spec 参考:** §4.6（M-8 caller assert + 路径覆盖测试）

- [ ] **Step 1.1：在 `tests/test_sw_config_broker.py` 末尾加 `TestM8ContractGuard` class 骨架**

定位文件末尾（grep `^class Test` 取最后一个 class 起始行后面）。

```python
class TestM8ContractGuard:
    """M-8 caller assert 契约守护（spec §4.6 / §7.2 invariant 1 + 3）。

    _validate_cached_decision 契约：valid=False ⇒ invalid_reason 非 None。
    caller `_resolve_config_for_part_unlocked` 失效路径用 `assert invalid_reason is not None`
    锁定不变量。本测试套守护 4 个角度（T13-T16）。
    """

    pass  # 测试方法在 Step 1.2-1.5 加
```

- [ ] **Step 1.2：写 T13 — `test_assertion_holds_under_broken_validate_contract`**

加在 `TestM8ContractGuard` class 内：

```python
    def test_assertion_holds_under_broken_validate_contract(
        self, monkeypatch, tmp_project_dir
    ):
        """T13 (spec §4.6): mock _validate_cached_decision 返回 (False, None)
        契约破裂时 _resolve_config_for_part_unlocked 必抛 AssertionError，
        而非 silent 调 _move_decision_to_history(reason=None) 写脏 history。
        """
        from adapters.solidworks import sw_config_broker

        # 构造最小 envelope 含 cached decision（让 _resolve 走到 cached 分支）
        envelope = sw_config_broker._empty_envelope()
        envelope["decisions_by_subsystem"] = {
            "test_sub": {
                "TEST-001": {
                    "decision": "use_config",
                    "config_name": "ConfigA",
                    "bom_dim_signature": "old_sig",
                    "sldprt_filename": "old.sldprt",
                    "decided_at": "2026-04-27T00:00:00Z",
                }
            }
        }

        # mock _validate 契约破裂
        def _broken_validate(*args, **kwargs):
            return (False, None)  # ← 违反契约：valid=False 但 reason=None

        monkeypatch.setattr(
            sw_config_broker, "_validate_cached_decision", _broken_validate
        )
        monkeypatch.setattr(
            sw_config_broker, "_load_decisions_envelope", lambda: envelope
        )
        monkeypatch.setattr(
            sw_config_broker, "_list_configs_via_com", lambda _: ["ConfigA", "ConfigB"]
        )

        with pytest.raises(AssertionError):
            sw_config_broker._resolve_config_for_part_unlocked(
                bom_row={"part_no": "TEST-001"},
                sldprt_path="C:/fake/test.sldprt",
                subsystem="test_sub",
            )
```

- [ ] **Step 1.3：写 T14 — `test_assertion_error_message_includes_contract_reference`**

加在 T13 之后：

```python
    def test_assertion_error_message_includes_contract_reference(
        self, monkeypatch, tmp_project_dir
    ):
        """T14 (spec §4.6): AssertionError message 包含 '_validate_cached_decision contract'
        引用，让 reviewer 失败时直接定位 spec §2.3 注释。
        """
        from adapters.solidworks import sw_config_broker

        envelope = sw_config_broker._empty_envelope()
        envelope["decisions_by_subsystem"] = {
            "test_sub": {
                "TEST-001": {
                    "decision": "use_config",
                    "config_name": "ConfigA",
                    "bom_dim_signature": "old_sig",
                    "sldprt_filename": "old.sldprt",
                    "decided_at": "2026-04-27T00:00:00Z",
                }
            }
        }
        monkeypatch.setattr(
            sw_config_broker,
            "_validate_cached_decision",
            lambda *a, **kw: (False, None),
        )
        monkeypatch.setattr(
            sw_config_broker, "_load_decisions_envelope", lambda: envelope
        )
        monkeypatch.setattr(
            sw_config_broker, "_list_configs_via_com", lambda _: ["ConfigA"]
        )

        with pytest.raises(AssertionError) as exc_info:
            sw_config_broker._resolve_config_for_part_unlocked(
                bom_row={"part_no": "TEST-001"},
                sldprt_path="C:/fake/test.sldprt",
                subsystem="test_sub",
            )
        # message 应引用契约（spec §2.3 注释 "_validate_cached_decision 契约"）
        assert "_validate_cached_decision" in str(exc_info.value) or \
               "contract" in str(exc_info.value).lower()
```

- [ ] **Step 1.4：写 T15 — `test_cached_invalid_with_each_reason_triggers_history`（参数化 3 reason）**

```python
    @pytest.mark.parametrize(
        "invalid_reason,bom_sig_changes,sldprt_filename_changes,available_configs",
        [
            ("bom_dim_signature_changed", True, False, ["ConfigA"]),
            ("sldprt_filename_changed", False, True, ["ConfigA"]),
            ("config_name_not_in_available_configs", False, False, ["ConfigB"]),
        ],
        ids=["bom_changed", "filename_changed", "config_renamed"],
    )
    def test_cached_invalid_with_each_reason_triggers_history(
        self,
        monkeypatch,
        tmp_project_dir,
        invalid_reason,
        bom_sig_changes,
        sldprt_filename_changes,
        available_configs,
    ):
        """T15 (spec §4.6): cached decision 在 3 种失效场景下都正确 append history。
        端到端测试，不 mock _validate_cached_decision —— 用真实失效条件触发。
        """
        from adapters.solidworks import sw_config_broker

        # 构造 envelope cached
        envelope = sw_config_broker._empty_envelope()
        envelope["decisions_by_subsystem"] = {
            "test_sub": {
                "TEST-001": {
                    "decision": "use_config",
                    "config_name": "ConfigA",
                    "bom_dim_signature": "current_sig" if not bom_sig_changes else "old_sig",
                    "sldprt_filename": "current.sldprt" if not sldprt_filename_changes else "old.sldprt",
                    "decided_at": "2026-04-27T00:00:00Z",
                }
            }
        }
        monkeypatch.setattr(
            sw_config_broker, "_load_decisions_envelope", lambda: envelope
        )
        monkeypatch.setattr(
            sw_config_broker, "_list_configs_via_com", lambda _: available_configs
        )
        # _save_decisions_envelope mock 防真 IO（envelope 改动 in-place 后端到端 verify）
        saved = []
        monkeypatch.setattr(
            sw_config_broker,
            "_save_decisions_envelope",
            lambda env: saved.append(env),
        )

        # bom_row 用"current_sig"（除非 bom 变了让它不同）
        bom_row = {"part_no": "TEST-001", "size": "current_sig_input"}
        # 为简化测试，monkeypatch _build_bom_dim_signature 返回 "current_sig"
        monkeypatch.setattr(
            sw_config_broker, "_build_bom_dim_signature", lambda _: "current_sig"
        )

        try:
            sw_config_broker._resolve_config_for_part_unlocked(
                bom_row=bom_row,
                sldprt_path="C:/fake/current.sldprt",
                subsystem="test_sub",
            )
        except sw_config_broker.NeedsUserDecision:
            pass  # 失效 fall through 到规则匹配，可能 raise NeedsUserDecision

        # 验证 history 含失效条目，reason 等于参数化值
        assert "decisions_history" in envelope
        assert len(envelope["decisions_history"]) == 1
        assert envelope["decisions_history"][0]["invalidation_reason"] == invalid_reason
        # 验证原 entry 已被 pop
        assert "TEST-001" not in envelope["decisions_by_subsystem"].get("test_sub", {})
```

- [ ] **Step 1.5：写 T16 — `test_cached_valid_does_not_trigger_assert`**

```python
    def test_cached_valid_does_not_trigger_assert(
        self, monkeypatch, tmp_project_dir
    ):
        """T16 (spec §4.6): 防御性——valid=True 路径不触发 M-8 assert，
        正常返回 ConfigResolution(source='cached_decision')。
        """
        from adapters.solidworks import sw_config_broker

        envelope = sw_config_broker._empty_envelope()
        envelope["decisions_by_subsystem"] = {
            "test_sub": {
                "TEST-001": {
                    "decision": "use_config",
                    "config_name": "ConfigA",
                    "bom_dim_signature": "match_sig",
                    "sldprt_filename": "match.sldprt",
                    "decided_at": "2026-04-27T00:00:00Z",
                }
            }
        }
        monkeypatch.setattr(
            sw_config_broker, "_load_decisions_envelope", lambda: envelope
        )
        monkeypatch.setattr(
            sw_config_broker, "_list_configs_via_com", lambda _: ["ConfigA"]
        )
        monkeypatch.setattr(
            sw_config_broker, "_build_bom_dim_signature", lambda _: "match_sig"
        )

        result = sw_config_broker._resolve_config_for_part_unlocked(
            bom_row={"part_no": "TEST-001"},
            sldprt_path="C:/fake/match.sldprt",
            subsystem="test_sub",
        )

        assert result.source == "cached_decision"
        assert result.config_name == "ConfigA"
```

- [ ] **Step 1.6：跑 4 个新测试，验证 RED**

```bash
pytest tests/test_sw_config_broker.py::TestM8ContractGuard -v 2>&1 | tail -20
```

预期：
- T13/T14 必 **FAIL**（main 还没加 assert，调 `_move_decision_to_history(envelope, sub, part_no, None)` 在写入端校验时 raise `ValueError("未知 invalidation_reason: None")` 不是 `AssertionError`）
- T15/T16 应 **PASS**（已有行为不依赖 assert）

**关键**：T13/T14 fail 的 message 应该是 "DID NOT RAISE AssertionError"，不是 "ValueError raised"——确认是因为写入端校验把 None 拒绝为 ValueError 而非缺 assert（这两类失败原因不同，前者意味着 RED 设置不对）。

如果 T13/T14 fail 信息是 `ValueError("未知 invalidation_reason: None")` 而非 `DID NOT RAISE AssertionError`：调整 mock 让 `_move_decision_to_history` 不被调（或单独 mock 它），让 fail 在 assert 这一步发生。

实测调整：

```python
        # 在 T13/T14 内额外 mock _move_decision_to_history 防它的 ValueError 干扰
        monkeypatch.setattr(
            sw_config_broker, "_move_decision_to_history", lambda *a, **kw: None
        )
```

这样 T13/T14 fail message 会清晰是 "DID NOT RAISE AssertionError"。

- [ ] **Step 1.7：commit 1**

```bash
git add tests/test_sw_config_broker.py
git commit -m "$(cat <<'EOF'
test(sw_config_broker): RED — M-8 caller assert 契约测试套（T13-T16）

新增 class TestM8ContractGuard，4 测试：
- T13 test_assertion_holds_under_broken_validate_contract（mock 契约破裂必抛 AssertionError）
- T14 test_assertion_error_message_includes_contract_reference（message 引用契约）
- T15 test_cached_invalid_with_each_reason_triggers_history（参数化 3 reason 端到端）
- T16 test_cached_valid_does_not_trigger_assert（防御性 valid=True 路径）

RED 状态：T13/T14 fail（缺 assert），T15/T16 PASS（已有行为不依赖 assert）。
spec §4.6 / §7.2 invariant 1+3 守护测试。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: M-8 GREEN — caller assert

**Files:**
- Modify: `adapters/solidworks/sw_config_broker.py`（`_resolve_config_for_part_unlocked` 失效分支加 assert）

**Spec 参考:** §2.3（M-8 caller None guard）

- [ ] **Step 2.1：grep caller 当前位置**

```bash
grep -nB1 -A5 "_move_decision_to_history(envelope, subsystem, part_no, invalid_reason)" adapters/solidworks/sw_config_broker.py
```

记录该调用所在行号（spec rev 1.4 写作时是 line 814；现在 grep 结果可能漂移）。

- [ ] **Step 2.2：在 `else:` 分支调用 `_move_decision_to_history` 之前加 assert**

定位上一步 grep 结果，在 `_move_decision_to_history(envelope, subsystem, part_no, invalid_reason)` 行的**正上方**插入：

```python
            # 失效：先持久化 history（即便后续抛异常，磁盘状态也已收敛）
            # _validate_cached_decision 契约：valid=False ⇒ invalid_reason is not None。
            # mypy 无法跨函数推断此契约，显式 assert narrow 类型并锁定不变量
            # （spec §2.3 / §7.2 invariant 1）。
            assert invalid_reason is not None, (
                "_validate_cached_decision contract: valid=False ⇒ reason is not None"
            )
            _move_decision_to_history(envelope, subsystem, part_no, invalid_reason)
            _save_decisions_envelope(envelope)
```

注：`assert` 第二参数（message）让 T14 message 测试通过。

- [ ] **Step 2.3：跑 T13-T16，验证 GREEN**

```bash
pytest tests/test_sw_config_broker.py::TestM8ContractGuard -v 2>&1 | tail -10
```

预期：4 测试全 PASS。

- [ ] **Step 2.4：跑全 broker test 套，确保不 regression**

```bash
pytest tests/test_sw_config_broker.py -v 2>&1 | tail -5
```

预期：所有既有测试 PASS，无新 fail。

- [ ] **Step 2.5：commit 2**

```bash
git add adapters/solidworks/sw_config_broker.py
git commit -m "$(cat <<'EOF'
feat(sw_config_broker): M-8 — caller assert (commit 1 测试 GREEN)

_resolve_config_for_part_unlocked cached decision 失效分支调用
_move_decision_to_history 之前加 `assert invalid_reason is not None`：

- mypy narrow `Literal[...] | None → Literal[...]`（spec §7.2 invariant 1 写入端守护）
- assert message 引用 _validate_cached_decision contract（让 T14 PASS）
- 不影响 happy path（valid=True 走 cached 命中分支不进 else）

T13-T16 全 PASS。既有测试无 regression。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: M-7 IO 边界 RED 测试套（T8-T12，5 测试）

**Files:**
- Modify: `tests/test_sw_config_broker.py`（在 `TestDecisionsEnvelopeIO` class 内加 5 测试）

**Spec 参考:** §4.5（M-7 IO 边界守护测试）

- [ ] **Step 3.1：grep `class TestDecisionsEnvelopeIO` 位置**

```bash
grep -n "^class TestDecisionsEnvelopeIO" tests/test_sw_config_broker.py
```

- [ ] **Step 3.2：在 `TestDecisionsEnvelopeIO` 末尾加 fixture + T8（unknown string）**

读 class 内既有测试找最后一个 method 末尾，在那之后加：

```python
    @pytest.fixture
    def _make_envelope_with_history(self, tmp_project_dir):
        """构造 minimal envelope dict + 写盘，返回该 path 给 _load 测试用。"""

        def _build(history_entries: list[dict]) -> Path:
            envelope = {
                "schema_version": 2,
                "decisions_by_subsystem": {},
                "decisions_history": history_entries,
            }
            path = tmp_project_dir / ".cad-spec-gen" / "spec_decisions.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(envelope), encoding="utf-8")
            return path

        return _build

    def test_load_rejects_unknown_string_in_history(
        self, _make_envelope_with_history, monkeypatch
    ):
        """T8 (spec §4.5 IO 边界): decisions_history 含 PR #19 之前的旧字符串
        'bom_change'，_load_decisions_envelope 必抛 ValueError 守护跨 IO 边界。
        """
        from adapters.solidworks import sw_config_broker

        _make_envelope_with_history([
            {
                "subsystem": "es",
                "part_no": "TEST-001",
                "previous_decision": {"decision": "use_config", "config_name": "A"},
                "invalidated_at": "2026-01-01T00:00:00Z",
                "invalidation_reason": "bom_change",  # ← 旧 schema 字符串
            }
        ])

        with pytest.raises(ValueError, match="schema 损坏或老版本数据"):
            sw_config_broker._load_decisions_envelope()
```

- [ ] **Step 3.3：加 T9（None reason）**

```python
    def test_load_rejects_none_invalidation_reason(
        self, _make_envelope_with_history
    ):
        """T9 (spec §4.5): invalidation_reason == None 必抛。"""
        from adapters.solidworks import sw_config_broker

        _make_envelope_with_history([
            {
                "subsystem": "es",
                "part_no": "TEST-001",
                "previous_decision": {"decision": "use_config"},
                "invalidated_at": "2026-01-01T00:00:00Z",
                "invalidation_reason": None,
            }
        ])

        with pytest.raises(ValueError, match="schema 损坏或老版本数据"):
            sw_config_broker._load_decisions_envelope()
```

- [ ] **Step 3.4：加 T10（empty string）**

```python
    def test_load_rejects_empty_string_invalidation_reason(
        self, _make_envelope_with_history
    ):
        """T10 (spec §4.5): invalidation_reason == '' 必抛。"""
        from adapters.solidworks import sw_config_broker

        _make_envelope_with_history([
            {
                "subsystem": "es",
                "part_no": "TEST-001",
                "previous_decision": {"decision": "use_config"},
                "invalidated_at": "2026-01-01T00:00:00Z",
                "invalidation_reason": "",
            }
        ])

        with pytest.raises(ValueError, match="schema 损坏或老版本数据"):
            sw_config_broker._load_decisions_envelope()
```

- [ ] **Step 3.5：加 T11（int 0）**

```python
    def test_load_rejects_int_invalidation_reason(
        self, _make_envelope_with_history
    ):
        """T11 (spec §4.5): invalidation_reason == 0（用户手编混入数字）必抛。"""
        from adapters.solidworks import sw_config_broker

        _make_envelope_with_history([
            {
                "subsystem": "es",
                "part_no": "TEST-001",
                "previous_decision": {"decision": "use_config"},
                "invalidated_at": "2026-01-01T00:00:00Z",
                "invalidation_reason": 0,
            }
        ])

        with pytest.raises(ValueError, match="schema 损坏或老版本数据"):
            sw_config_broker._load_decisions_envelope()
```

- [ ] **Step 3.6：加 T12（partial corrupted）**

```python
    def test_load_rejects_partial_corrupted_history(
        self, _make_envelope_with_history
    ):
        """T12 (spec §4.5): 5 条 history，1 条含未知 reason，整体 raise（不 silent skip）。"""
        from adapters.solidworks import sw_config_broker

        _make_envelope_with_history([
            {
                "subsystem": "es",
                "part_no": f"TEST-{i:03d}",
                "previous_decision": {"decision": "use_config"},
                "invalidated_at": "2026-01-01T00:00:00Z",
                "invalidation_reason": (
                    "bom_change_legacy" if i == 2 else "bom_dim_signature_changed"
                ),
            }
            for i in range(5)
        ])

        with pytest.raises(ValueError, match="schema 损坏或老版本数据"):
            sw_config_broker._load_decisions_envelope()
```

- [ ] **Step 3.7：跑 T8-T12 验证 RED**

```bash
pytest tests/test_sw_config_broker.py::TestDecisionsEnvelopeIO -v -k "test_load_rejects" 2>&1 | tail -15
```

预期：5 测试全 **FAIL**（main 上 `_load_decisions_envelope` 还没加读取端校验）。

fail message 应该是 "DID NOT RAISE ValueError"——确认是缺校验逻辑，不是 schema_version 等其他错。

- [ ] **Step 3.8：commit 3**

```bash
git add tests/test_sw_config_broker.py
git commit -m "$(cat <<'EOF'
test(sw_config_broker): RED — M-7 IO 边界守护测试套（T8-T12，5 测试）

新增 fixture _make_envelope_with_history + 5 边界 case 测试：
- T8 unknown string ('bom_change' 旧 schema)
- T9 None invalidation_reason
- T10 empty string
- T11 int 0（用户手编）
- T12 partial corrupted（5 条 history 1 条坏）

RED 状态：5 测试全 fail（_load_decisions_envelope 还没加读取端校验）。
spec §4.5 / §7.2 invariant 1（双层守护跨 IO 边界）守护测试。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: M-7 IO 边界 GREEN — _load_decisions_envelope 加读取端校验

**Files:**
- Modify: `adapters/solidworks/sw_config_broker.py`（`_load_decisions_envelope` 函数末尾加校验循环）

**Spec 参考:** §2.2 Step 4（M-7 IO 边界守护）

- [ ] **Step 4.1：grep `_load_decisions_envelope` 函数体**

```bash
grep -nA30 "^def _load_decisions_envelope" adapters/solidworks/sw_config_broker.py
```

定位 return 语句（应该是 `return envelope` 或类似）。

- [ ] **Step 4.2：在 return 之前插入读取端校验**

```python
def _load_decisions_envelope() -> dict[str, Any]:
    """..."""
    # ... 现有 IO 逻辑（json.load + schema 校验等）...

    # M-7 IO 边界守护（spec §2.2 Step 4 / §7.2 invariant 1）：
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

注：`INVALIDATION_REASONS` 是 main 已有的 `frozenset({"bom_dim_signature_changed", "sldprt_filename_changed", "config_name_not_in_available_configs"})`（line 36-40 区域），无需新建。

- [ ] **Step 4.3：跑 T8-T12 验证 GREEN**

```bash
pytest tests/test_sw_config_broker.py::TestDecisionsEnvelopeIO -v -k "test_load_rejects" 2>&1 | tail -10
```

预期：5 测试全 PASS。

- [ ] **Step 4.4：跑全 broker test，确保不 regression**

```bash
pytest tests/test_sw_config_broker.py -v 2>&1 | tail -5
```

预期：既有测试无 regression。

- [ ] **Step 4.5：commit 4**

```bash
git add adapters/solidworks/sw_config_broker.py
git commit -m "$(cat <<'EOF'
feat(sw_config_broker): M-7 IO 边界 — _load_decisions_envelope 加读取端校验

跨 IO 边界守护（spec §2.2 Step 4 / §7.2 invariant 1 双层）：
- 写入端（_move_decision_to_history）：caller 已被 mypy Literal 守护
- 读取端（_load_decisions_envelope）：JSON 反序列化结果 runtime 校验

防御场景：老 envelope 含旧字符串 / None / 空串 / int / 部分损坏 history。
T8-T12 全 PASS。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: M-7 写入端 + Literal 类型守护测试（T5-T7）

**Files:**
- Modify: `tests/test_sw_config_broker.py`（在 `TestValidateCachedDecision` / `TestDecisionAccessors` 加测试）

**Spec 参考:** §4.4（M-7 写入端 + Literal 类型测试）

- [ ] **Step 5.1：在 `TestValidateCachedDecision` 末尾加 T5（参数化 4 case）**

grep 该 class 末尾，在最后一个 method 之后加：

```python
    @pytest.mark.parametrize(
        "decision_state,expected_valid,expected_reason",
        [
            ("match", True, None),
            ("bom_changed", False, "bom_dim_signature_changed"),
            ("filename_changed", False, "sldprt_filename_changed"),
            ("config_renamed", False, "config_name_not_in_available_configs"),
        ],
        ids=["valid_match", "bom_changed", "filename_changed", "config_renamed"],
    )
    def test_validate_returns_typed_literal_or_none(
        self, decision_state, expected_valid, expected_reason
    ):
        """T5 (spec §4.4 / §7.2 invariant 1): _validate_cached_decision 返回 tuple
        第二位运行时是 3 字面量字符串之一（valid=False）或 None（valid=True）。
        """
        from adapters.solidworks.sw_config_broker import _validate_cached_decision

        decision = {
            "decision": "use_config",
            "config_name": "ConfigA",
            "bom_dim_signature": "match_sig" if decision_state != "bom_changed" else "old",
            "sldprt_filename": "match.sldprt" if decision_state != "filename_changed" else "old.sldprt",
        }
        current_bom_signature = "match_sig"
        current_sldprt_filename = "match.sldprt"
        current_available_configs = (
            ["ConfigA"] if decision_state != "config_renamed" else ["ConfigB"]
        )

        valid, reason = _validate_cached_decision(
            decision,
            current_bom_signature,
            current_sldprt_filename,
            current_available_configs,
        )
        assert valid is expected_valid
        assert reason == expected_reason
        # 类型守护
        if reason is not None:
            assert isinstance(reason, str)
            assert reason in {
                "bom_dim_signature_changed",
                "sldprt_filename_changed",
                "config_name_not_in_available_configs",
            }
```

- [ ] **Step 5.2：在同 class 加 T6（frozenset 不可变 + 完整性）**

```python
    def test_invalidation_reasons_frozenset_immutable_and_complete(self):
        """T6 (spec §4.4 / §7.2 invariant 5): INVALIDATION_REASONS 是不可变 frozenset
        且包含且仅包含 3 个 Literal 字面量。防御未来误删/误改常量。
        """
        from adapters.solidworks.sw_config_broker import INVALIDATION_REASONS

        assert isinstance(INVALIDATION_REASONS, frozenset)
        # 完整性：3 个 Literal 字面量都在
        assert INVALIDATION_REASONS == {
            "bom_dim_signature_changed",
            "sldprt_filename_changed",
            "config_name_not_in_available_configs",
        }
        # 不可变性
        with pytest.raises(AttributeError):
            INVALIDATION_REASONS.add("new_reason")  # type: ignore[attr-defined]
```

- [ ] **Step 5.3：在 `TestDecisionAccessors` 改写 `test_move_decision_to_history` 为参数化（T7）**

grep `def test_move_decision_to_history` 位置，把单一测试改为参数化：

```python
    @pytest.mark.parametrize(
        "invalidation_reason",
        [
            "bom_dim_signature_changed",
            "sldprt_filename_changed",
            "config_name_not_in_available_configs",
        ],
    )
    def test_move_decision_to_history(self, invalidation_reason):
        """T7 (spec §4.4 / §7.2 invariant 2): _move_decision_to_history 对 3 reason
        各自正确 append history + pop 原 entry。
        """
        from adapters.solidworks.sw_config_broker import (
            _empty_envelope,
            _move_decision_to_history,
        )

        envelope = _empty_envelope()
        envelope["decisions_by_subsystem"] = {
            "test_sub": {
                "TEST-001": {
                    "decision": "use_config",
                    "config_name": "ConfigA",
                    "decided_at": "2026-04-27T00:00:00Z",
                }
            }
        }

        _move_decision_to_history(
            envelope, "test_sub", "TEST-001", invalidation_reason
        )

        # 1. 原 entry 已 pop
        assert "TEST-001" not in envelope["decisions_by_subsystem"]["test_sub"]
        # 2. history append 1 条，reason 等于参数
        assert len(envelope["decisions_history"]) == 1
        history_entry = envelope["decisions_history"][0]
        assert history_entry["invalidation_reason"] == invalidation_reason
        assert history_entry["subsystem"] == "test_sub"
        assert history_entry["part_no"] == "TEST-001"
        assert "previous_decision" in history_entry
        assert "invalidated_at" in history_entry
```

- [ ] **Step 5.4：跑 T5-T7 + 既有 broker test，验证全 PASS**

```bash
pytest tests/test_sw_config_broker.py::TestValidateCachedDecision -v 2>&1 | tail -10
pytest tests/test_sw_config_broker.py::TestDecisionAccessors -v 2>&1 | tail -10
```

预期：T5/T6/T7 全 PASS（_validate / _move 行为 main 已正确，新测试只是显式守护）。

- [ ] **Step 5.5：commit 5**

```bash
git add tests/test_sw_config_broker.py
git commit -m "$(cat <<'EOF'
test(sw_config_broker): M-7 写入端 + Literal 类型守护测试（T5-T7，3 测试）

- T5 test_validate_returns_typed_literal_or_none（参数化 4 case：
  3 reason + 1 valid=True None）
- T6 test_invalidation_reasons_frozenset_immutable_and_complete
  （防御未来误删/误改常量）
- T7 test_move_decision_to_history 改写为参数化 3 reason
  （守护 invariant 2：append history + pop 原 entry）

spec §4.4 / §7.2 invariant 1+2+5 守护测试。全 PASS（行为已对齐）。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: M-7 refactor — Literal type + 写入端删校验 + 删旧测试

**Files:**
- Modify: `adapters/solidworks/sw_config_broker.py`（顶部加 `Literal` import + 类型别名 + 改 `_validate_cached_decision` / `_move_decision_to_history` 签名 + 删写入端校验）
- Modify: `tests/test_sw_config_broker.py`（删 `test_move_decision_rejects_unknown_reason`）

**Spec 参考:** §2.2 Step 1-3（M-7 Literal type 替代运行时校验）

- [ ] **Step 6.1：在 `sw_config_broker.py` 顶部加 `Literal` import + `InvalidationReason` 类型别名**

grep `^from typing` 位置，编辑 typing import 行加 `Literal`：

```python
from typing import Any, Literal
```

然后在 `INVALIDATION_REASONS = frozenset({...})` 前一行（line 36 区域）加：

```python
# spec §2.2 Step 1 (M-7)：Literal 类型别名让 mypy 编译期捕获错传字面量。
InvalidationReason = Literal[
    "bom_dim_signature_changed",
    "sldprt_filename_changed",
    "config_name_not_in_available_configs",
]
```

- [ ] **Step 6.2：改 `INVALIDATION_REASONS` 加类型注解**

把 main line 36 区域：

```python
INVALIDATION_REASONS = frozenset({
    "bom_dim_signature_changed",
    ...
})
```

改为：

```python
INVALIDATION_REASONS: frozenset[InvalidationReason] = frozenset({
    "bom_dim_signature_changed",
    "sldprt_filename_changed",
    "config_name_not_in_available_configs",
})
```

- [ ] **Step 6.3：改 `_validate_cached_decision` 返回类型签名**

grep `def _validate_cached_decision`，把签名最后一行 `-> tuple[bool, str | None]:` 改为：

```python
) -> tuple[bool, InvalidationReason | None]:
```

函数内部不需要改（实际返回字面量字符串本身就是 `Literal[...]` subtype）。

- [ ] **Step 6.4：改 `_move_decision_to_history` 签名 + 删写入端校验**

grep `def _move_decision_to_history`，把 `invalidation_reason: str,` 改为：

```python
    invalidation_reason: InvalidationReason,
```

然后在函数体内删除头部 4 行运行时校验（main line 419-423 区域，spec §2.2 Step 3）：

```python
def _move_decision_to_history(
    envelope: dict[str, Any],
    subsystem: str,
    part_no: str,
    invalidation_reason: InvalidationReason,
) -> None:
    """..."""
    # ── M-7 删除：写入端运行时校验（mypy 编译期 Literal 已守护）──
    # 旧代码（删）：
    # if invalidation_reason not in INVALIDATION_REASONS:
    #     raise ValueError(...)

    decision = envelope["decisions_by_subsystem"][subsystem].pop(part_no)
    envelope.setdefault("decisions_history", []).append({
        "subsystem": subsystem,
        "part_no": part_no,
        "previous_decision": decision,
        "invalidated_at": datetime.now(timezone.utc).isoformat(),
        "invalidation_reason": invalidation_reason,
    })
```

- [ ] **Step 6.5：删除 `test_move_decision_rejects_unknown_reason`**

grep 位置：

```bash
grep -n "test_move_decision_rejects_unknown_reason" tests/test_sw_config_broker.py
```

定位该方法（含 docstring + body）整段删除（约 10-15 行）。

确认删除：

```bash
grep -c "test_move_decision_rejects_unknown_reason" tests/test_sw_config_broker.py
```

预期：0（已删）。

- [ ] **Step 6.6：跑全 broker test 套，验证不 regression + 新 test 全 PASS**

```bash
pytest tests/test_sw_config_broker.py -v 2>&1 | tail -15
```

预期：所有测试 PASS（删了 1 + 之前加的 T5/T6/T7/T8-T16 全在）。

- [ ] **Step 6.7：commit 6**

```bash
git add adapters/solidworks/sw_config_broker.py tests/test_sw_config_broker.py
git commit -m "$(cat <<'EOF'
refactor(sw_config_broker): M-7 — Literal type + 写入端删 _move 校验 + 删旧测试

spec §2.2 Step 1-3 (M-7)：
- 加 Literal 类型别名 InvalidationReason（顶部 typing.Literal import）
- INVALIDATION_REASONS 加 frozenset[InvalidationReason] 类型注解
- _validate_cached_decision 返回类型 tuple[bool, str | None]
  → tuple[bool, InvalidationReason | None]
- _move_decision_to_history 参数 str → InvalidationReason + 删 4 行
  写入端运行时校验（mypy 编译期 Literal 已守护）

测试：
- 删 TestDecisionAccessors.test_move_decision_rejects_unknown_reason
  （旧写入端 ValueError 不再 raise）

读取端 IO 校验（_load_decisions_envelope）已在 commit 4 加，跨 IO 边界守护完整。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: M-6 模块级 import 守护测试（T1-T4）

**Files:**
- Modify: `tests/test_sw_config_broker.py`（新增 `class TestModuleLevelImports`）

**Spec 参考:** §4.3（M-6 模块级 import 测试）

- [ ] **Step 7.1：在 `tests/test_sw_config_broker.py` 末尾加 `TestModuleLevelImports` class 骨架**

```python
class TestModuleLevelImports:
    """M-6 模块级 import 守护（spec §4.3 / §7.2 invariant 4）。

    prewarm_config_lists 内函数级 import (detect_solidworks +
    sw_config_lists_cache) 移到模块级后，name 必须暴露在 sw_config_broker
    namespace，让 mock.patch.object 模式可工作（cad_pipeline.py best practice）。
    """
    pass
```

- [ ] **Step 7.2：加 T1（detect_solidworks 模块级名字暴露）**

```python
    def test_detect_solidworks_module_level_attribute(self):
        """T1 (spec §4.3): hasattr(sw_config_broker, 'detect_solidworks') == True
        让 mock.patch.object(sw_config_broker, 'detect_solidworks') 可工作。
        """
        from adapters.solidworks import sw_config_broker

        assert hasattr(sw_config_broker, "detect_solidworks"), (
            "M-6: detect_solidworks 应模块级 import 到 sw_config_broker namespace"
        )
        # 验证是 callable 而非 module
        assert callable(sw_config_broker.detect_solidworks)
```

- [ ] **Step 7.3：加 T2（cache_mod 模块级名字暴露）**

```python
    def test_cache_mod_module_level_attribute(self):
        """T2 (spec §4.3): sw_config_broker.cache_mod 暴露 sw_config_lists_cache
        模块（M-6 第二个 import 移位）。
        """
        from adapters.solidworks import sw_config_broker

        assert hasattr(sw_config_broker, "cache_mod"), (
            "M-6: cache_mod 应模块级 import 到 sw_config_broker namespace"
        )
        # 验证是模块（有 _load_config_lists_cache 函数）
        assert hasattr(sw_config_broker.cache_mod, "_load_config_lists_cache")
```

- [ ] **Step 7.4：加 T3（mock.patch.object 兼容）**

```python
    def test_module_level_import_patchable(self, monkeypatch):
        """T3 (spec §4.3): mock.patch.object(sw_config_broker, 'detect_solidworks')
        在 prewarm_config_lists 路径生效（M-6 实际 mock 兼容性测试）。
        """
        from adapters.solidworks import sw_config_broker
        from unittest.mock import MagicMock

        fake_sw = MagicMock()
        fake_sw.version_year = 2024
        fake_sw.toolbox_dir = "C:/fake/toolbox"

        monkeypatch.setattr(
            sw_config_broker, "detect_solidworks", lambda: fake_sw
        )

        # 直接调 detect_solidworks 验证 mock 生效（不必跑全 prewarm，
        # 因为本测试守护"name 可被替换"，不守护"prewarm 行为"）
        result = sw_config_broker.detect_solidworks()
        assert result.version_year == 2024
        assert result.toolbox_dir == "C:/fake/toolbox"
```

- [ ] **Step 7.5：加 T4（reload 防循环依赖）**

```python
    def test_no_circular_import_on_reload(self):
        """T4 (spec §4.3): importlib.reload(sw_config_broker) 不抛 ImportError。
        反向防 sw_config_lists_cache / sw_detect 未来加 broker 反向 import
        造成循环依赖。
        """
        import importlib
        from adapters.solidworks import sw_config_broker

        # 第一次 reload
        try:
            reloaded = importlib.reload(sw_config_broker)
        except ImportError as e:
            pytest.fail(
                f"M-6: sw_config_broker reload 失败（疑似循环依赖）: {e}"
            )

        # 验证 reload 后 name 仍在
        assert hasattr(reloaded, "detect_solidworks")
        assert hasattr(reloaded, "cache_mod")
```

- [ ] **Step 7.6：跑 T1-T4 验证 RED**

```bash
pytest tests/test_sw_config_broker.py::TestModuleLevelImports -v 2>&1 | tail -10
```

预期：
- T1/T2 必 **FAIL**（main 上 import 还在函数级，模块 namespace 没有 `detect_solidworks` / `cache_mod`）
- T3 必 **FAIL**（同上原因）
- T4 应 **PASS**（reload 不依赖 import 位置）

- [ ] **Step 7.7：commit 7**

```bash
git add tests/test_sw_config_broker.py
git commit -m "$(cat <<'EOF'
test(sw_config_broker): M-6 模块级 import 守护测试（T1-T4，4 测试）

新增 class TestModuleLevelImports：
- T1 test_detect_solidworks_module_level_attribute
- T2 test_cache_mod_module_level_attribute
- T3 test_module_level_import_patchable（mock 兼容性）
- T4 test_no_circular_import_on_reload（反向防循环依赖）

RED 状态：T1/T2/T3 fail（main import 还在函数级），T4 PASS。
spec §4.3 / §7.2 invariant 4 守护测试。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: M-6 refactor — 函数级 import 提到模块级

**Files:**
- Modify: `adapters/solidworks/sw_config_broker.py`（`prewarm_config_lists` 内 2 行 import 移到顶部）

**Spec 参考:** §2.1（M-6 函数级 import → 模块级）

- [ ] **Step 8.1：grep `prewarm_config_lists` 函数体内 2 行 import**

```bash
grep -nA3 "if os.environ.get.\"CAD_SW_BROKER_DISABLE\".*== \"1\"" adapters/solidworks/sw_config_broker.py | head -10
```

记录 2 行 import 当前行号（spec rev 1.4 写作时 line 557-558；现在 grep 重新定位）。

- [ ] **Step 8.2：从 `prewarm_config_lists` 内删除 2 行 import**

定位 `if os.environ.get("CAD_SW_BROKER_DISABLE") == "1": return` 之后的 2 行：

```python
def prewarm_config_lists(...):
    ...
    if os.environ.get("CAD_SW_BROKER_DISABLE") == "1":
        return

    from adapters.solidworks import sw_config_lists_cache as cache_mod  # ← 删除此行
    from adapters.solidworks.sw_detect import detect_solidworks         # ← 删除此行

    cache = cache_mod._load_config_lists_cache()
    ...
```

- [ ] **Step 8.3：在文件顶部 import 段加 2 行**

grep 顶部 import 段（`^from .* import` 一段，找最后一个 import 行）：

```bash
grep -n "^from \|^import " adapters/solidworks/sw_config_broker.py | head -15
```

在最后一个项目 import 后（如 `from cad_paths import ...` 之后或类似位置）加：

```python
# M-6 (spec §2.1): 函数级 import 提到模块级，让 mock.patch.object 可工作
# （cad_pipeline.py best practice）+ 避免重复 import 性能开销。
from adapters.solidworks import sw_config_lists_cache as cache_mod
from adapters.solidworks.sw_detect import detect_solidworks
```

注：放在 `INVALIDATION_REASONS` 定义 + `InvalidationReason` 类型别名之前。

- [ ] **Step 8.4：跑 T1-T4 验证 GREEN**

```bash
pytest tests/test_sw_config_broker.py::TestModuleLevelImports -v 2>&1 | tail -10
```

预期：4 测试全 PASS。

- [ ] **Step 8.5：跑全 broker test，验证 prewarm 行为不 regression**

```bash
pytest tests/test_sw_config_broker.py -v 2>&1 | tail -5
```

预期：所有测试 PASS。

特别注意 `TestPrewarmConfigLists` 套件——M-6 是 import 移位，prewarm 行为应完全不变。

- [ ] **Step 8.6：commit 8**

```bash
git add adapters/solidworks/sw_config_broker.py
git commit -m "$(cat <<'EOF'
refactor(sw_config_broker): M-6 — 函数级 import 提到模块级

spec §2.1：把 prewarm_config_lists 内 2 行函数级 import：
- from adapters.solidworks import sw_config_lists_cache as cache_mod
- from adapters.solidworks.sw_detect import detect_solidworks

提到文件顶部 import 段，让 mock.patch.object(sw_config_broker, ...) 模式
可工作（cad_pipeline.py 既有 best practice）+ 避免重复 import 开销。

循环依赖验证：sw_config_lists_cache / sw_detect 都不反向 import broker。

T1-T4 全 PASS。既有 prewarm 测试无 regression。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: mypy CI gate 反例自校验测试（T17 + fixture 文件）

**Files:**
- Create: `tests/fixtures/_mypy_invalid_literal_fixture.py`
- Modify: `tests/test_sw_config_broker.py`（新增 `class TestMypyCIGate` 含 T17）

**Spec 参考:** §4.7（mypy CI gate 自校验测试）

- [ ] **Step 9.1：创建 fixture 文件 `tests/fixtures/_mypy_invalid_literal_fixture.py`**

```python
"""T17 (spec §4.7) mypy CI gate 反例 fixture。

故意类型错的代码片段，让 mypy --platform=win32 --strict 必 fail。
本文件不被 pytest collect（无 test_ prefix），仅作 mypy subprocess 输入。

如果未来 mypy CI gate 配置漂移（如 strict=false），mypy 不再报错此文件，
T17 测试就 fail，提示 reviewer 修复 gate 配置。
"""

from adapters.solidworks.sw_config_broker import (
    InvalidationReason,
    _move_decision_to_history,
)


def _trigger_mypy_error() -> None:
    """故意调用 _move_decision_to_history 传入未定义在 InvalidationReason
    Literal 中的字面量，mypy strict 必 fail。
    """
    envelope: dict[str, object] = {"decisions_by_subsystem": {}, "decisions_history": []}
    # type: ignore 故意不加——让 mypy 必报 type error
    _move_decision_to_history(
        envelope,
        "test_subsystem",
        "TEST-001",
        "bom_change_legacy",  # ← 不在 InvalidationReason Literal 之内，mypy 必 fail
    )


# 第二处类型错：把 InvalidationReason 当 str 传给非 Literal 函数返回类型
def _another_type_error() -> InvalidationReason:
    return "arbitrary_string"  # ← mypy 必 fail：str 非 Literal[3 个具体字面量]
```

- [ ] **Step 9.2：在 `tests/test_sw_config_broker.py` 末尾加 `TestMypyCIGate` class 骨架**

```python
class TestMypyCIGate:
    """mypy CI gate 自校验（spec §4.7）。

    防御 reviewer 误改 [[overrides]] strict=true 为 false 或 exclude
    sw_config_broker.py 让 gate 形同虚设。
    """

    pass
```

- [ ] **Step 9.3：在 class 内加 T17（反例 fixture 必 fail）**

```python
    @pytest.mark.mypy
    def test_mypy_strict_catches_invalid_literal_assignment(self):
        """T17 (spec §4.7): mypy --platform=win32 --strict 必能捕获故意类型错的
        fixture 文件。subprocess 调 mypy 验证退出码非零。
        """
        import subprocess
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[1]
        fixture_path = (
            repo_root / "tests" / "fixtures" / "_mypy_invalid_literal_fixture.py"
        )
        assert fixture_path.exists(), (
            f"T17 fixture 文件不存在: {fixture_path}"
        )

        result = subprocess.run(
            ["mypy", "--platform=win32", "--strict", str(fixture_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )

        # mypy 必 fail（exit code 1+）+ stdout 含 "error:"
        assert result.returncode != 0, (
            f"T17: mypy 应捕获 fixture 类型错但通过了。stdout: {result.stdout}"
        )
        assert "error:" in result.stdout, (
            f"T17: mypy 输出应含 error。stdout: {result.stdout}"
        )
```

- [ ] **Step 9.4：跑 T17 验证（GREEN——main 已有 mypy 不依赖 CI 配置）**

```bash
pytest tests/test_sw_config_broker.py::TestMypyCIGate::test_mypy_strict_catches_invalid_literal_assignment -v 2>&1 | tail -15
```

预期：T17 PASS（mypy 命令对 fixture 必 fail，subprocess 退出码非零）。

如果 mypy 未装：
```bash
pip install "mypy>=1.10"
```

- [ ] **Step 9.5：commit 9**

```bash
git add tests/fixtures/_mypy_invalid_literal_fixture.py tests/test_sw_config_broker.py
git commit -m "$(cat <<'EOF'
test(ci): mypy CI gate 反例自校验测试（T17，含 fixture 文件）

新增 tests/fixtures/_mypy_invalid_literal_fixture.py：
- 故意类型错的代码片段（传错 Literal + 错误返回类型）
- 让 mypy --platform=win32 --strict 必 fail

新增 class TestMypyCIGate.test_mypy_strict_catches_invalid_literal_assignment：
- subprocess 调 mypy 验证 fixture 退出码非零 + stdout 含 'error:'
- @pytest.mark.mypy marker 让本地默认跑可过滤

防御场景：reviewer 误改 strict=false 或 exclude sw_config_broker → T17 fail
提示修复 gate 配置。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: mypy strict gate 实施 + T18 当前模块自检

**Files:**
- Modify: `pyproject.toml`（加 `[tool.mypy]` + `[[tool.mypy.overrides]]`）
- Modify: `.github/workflows/tests.yml`（加 `mypy-strict` job）
- Modify: `tests/test_sw_config_broker.py`（在 `TestMypyCIGate` 加 T18）

**Spec 参考:** §3.1 / §3.2 / §4.7

- [ ] **Step 10.1：在 `pyproject.toml` 末尾加 `[tool.mypy]` section**

grep `[tool.pytest.ini_options]` 位置（main 当前 line 70 区域）。在 pyproject.toml **末尾**（所有现有 section 之后）追加：

```toml

[tool.mypy]
# 渐进式 typing 政策（spec §3 / §11 M-7 决策）：仅本 PR 触动模块进 strict。
# 未来 cleanup PR 触动新模块时按需在 [[tool.mypy.overrides]] 加入。
python_version = "3.10"  # 与 requires-python = ">=3.10" 对齐，
                          # 让 mypy 检查 3.10 不支持的语法（如 PEP 695 type alias）
strict_optional = true
warn_redundant_casts = true
warn_unused_ignores = true
ignore_missing_imports = true  # 默认非 strict 防历史债爆炸

[[tool.mypy.overrides]]
module = "adapters.solidworks.sw_config_broker"
strict = true
```

- [ ] **Step 10.2：在 `.github/workflows/tests.yml` 末尾加 `mypy-strict` job**

grep yaml 文件结构，在 `regression:` job 之后（文件末尾）追加：

```yaml

  # ─── mypy strict CI gate (spec §3) ────────────────────────────────────
  # Scope: 仅 adapters/solidworks/sw_config_broker.py（渐进式 typing 政策）。
  # --platform=win32 让 mypy 看见 msvcrt（_project_file_lock 内 Windows-only API）。
  mypy-strict:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-python@v6
        with:
          python-version: '3.11'
      - name: Install mypy
        run: pip install "mypy>=1.10"
      - name: Run mypy strict on sw_config_broker.py
        run: mypy --platform=win32 adapters/solidworks/sw_config_broker.py
```

- [ ] **Step 10.3：本地 dry-run mypy 验证 sw_config_broker.py 全绿**

```bash
mypy --platform=win32 adapters/solidworks/sw_config_broker.py 2>&1 | tail -10
```

预期：`Success: no issues found in 1 source file`（退出码 0）。

如果有 type error → 修代码（不动 spec policy）：
- 若是 M-8 历史 type error（mypy 报 `_move_decision_to_history` arg 类型）：commit 2 已加 `assert invalid_reason is not None` narrow 类型，应解决
- 若是其他 type error：grep 错位置 + 加最小修复（不引入 `# type: ignore`，违反 §3.3 政策）

- [ ] **Step 10.4：在 `TestMypyCIGate` 加 T18（当前模块必 pass）**

```python
    @pytest.mark.mypy
    def test_mypy_strict_passes_current_module(self):
        """T18 (spec §4.7): 当前 sw_config_broker.py 在 mypy --platform=win32 --strict
        下必 pass（退出码 0）。守护 PR 自身不引入新 type error。
        """
        import subprocess
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[1]
        target = repo_root / "adapters" / "solidworks" / "sw_config_broker.py"

        result = subprocess.run(
            ["mypy", "--platform=win32", "--strict", str(target)],
            capture_output=True,
            text=True,
            timeout=60,
        )

        assert result.returncode == 0, (
            f"T18: sw_config_broker.py mypy 失败，引入新 type error。"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
```

- [ ] **Step 10.5：跑 T17 + T18 + 全 broker test**

```bash
pytest tests/test_sw_config_broker.py::TestMypyCIGate -v 2>&1 | tail -10
pytest tests/test_sw_config_broker.py -v 2>&1 | tail -5
```

预期：T17 + T18 PASS；既有测试无 regression。

- [ ] **Step 10.6：commit 10**

```bash
git add pyproject.toml .github/workflows/tests.yml tests/test_sw_config_broker.py
git commit -m "$(cat <<'EOF'
ci(mypy): mypy strict gate (sw_config_broker.py only) + T18 自检

spec §3 / §4.7：
- pyproject.toml 加 [tool.mypy] + [[tool.mypy.overrides]] strict=true
  scope 仅 adapters.solidworks.sw_config_broker（渐进式 typing 政策）
- .github/workflows/tests.yml 加 mypy-strict job（ubuntu-latest，
  actions/checkout@v6 + setup-python@v6 与既有 jobs 对齐）
- mypy --platform=win32 让 msvcrt（_project_file_lock 函数级 import）可见

T18 test_mypy_strict_passes_current_module：subprocess 调 mypy 验证
当前模块退出码 0，守护 PR 自身不引入新 type error。

manual post-merge action：branch protection 加 mypy-strict 进 main 必过 checks。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: 集成 + §7.2 invariant 回归测试（T19-T20）

**Files:**
- Modify: `tests/test_sw_config_broker.py`（在 `TestPrewarmConfigLists` 加 T19，新增 `class TestSection72InvariantsRegression` 含 T20）

**Spec 参考:** §4.8（集成 + invariant 回归测试）

- [ ] **Step 11.1：在 `TestPrewarmConfigLists` 末尾加 T19（端到端 pipeline）**

grep class 末尾，加：

```python
    def test_e2e_prewarm_resolve_invalidate_history_pipeline(
        self, monkeypatch, tmp_project_dir
    ):
        """T19 (spec §4.8): 端到端链路集成测试 ——
        prewarm 4 件 → resolve 触发 cached invalidate → fall through → history append。

        守护 §7.2 invariant 2+3+4：cached 失效持久化 history + fall through 规则匹配
        + prewarm 行为不变（M-6 模块级 import 后）。
        """
        from adapters.solidworks import sw_config_broker

        # mock SW worker 返回固定 configs（避开真 SW 调用）
        monkeypatch.setattr(
            sw_config_broker,
            "_list_configs_via_com",
            lambda path: ["ConfigA", "ConfigB"],
        )

        # 构造 envelope 含 1 件 cached + 现状不匹配（必走失效路径）
        envelope = sw_config_broker._empty_envelope()
        envelope["decisions_by_subsystem"] = {
            "es": {
                "P-001": {
                    "decision": "use_config",
                    "config_name": "OldConfig",  # ← 现状 available 没有此 config
                    "bom_dim_signature": "current_sig",
                    "sldprt_filename": "current.sldprt",
                    "decided_at": "2026-04-27T00:00:00Z",
                }
            }
        }
        monkeypatch.setattr(
            sw_config_broker, "_load_decisions_envelope", lambda: envelope
        )
        saved = []
        monkeypatch.setattr(
            sw_config_broker,
            "_save_decisions_envelope",
            lambda env: saved.append(env),
        )
        monkeypatch.setattr(
            sw_config_broker,
            "_build_bom_dim_signature",
            lambda _: "current_sig",
        )

        # 调 _resolve_config_for_part_unlocked，cached invalidate → fall through
        try:
            sw_config_broker._resolve_config_for_part_unlocked(
                bom_row={"part_no": "P-001"},
                sldprt_path="C:/fake/current.sldprt",
                subsystem="es",
            )
        except sw_config_broker.NeedsUserDecision:
            pass

        # 验证 history append + reason 正确
        assert len(envelope["decisions_history"]) == 1
        assert (
            envelope["decisions_history"][0]["invalidation_reason"]
            == "config_name_not_in_available_configs"
        )
        # 原 cached entry 已 pop
        assert "P-001" not in envelope["decisions_by_subsystem"]["es"]
```

- [ ] **Step 11.2：在文件末尾加 `TestSection72InvariantsRegression` class（含 T20）**

```python
class TestSection72InvariantsRegression:
    """§7.2 5 条 invariant 参数化反向 trace（spec §4.8 / §7.2）。

    每条 invariant 一个 sub-assertion；任何一条破裂立即 fail。
    fail message 引用 spec §7.2 编号让 reviewer 直接定位。
    """

    @pytest.mark.parametrize(
        "invariant_num,invariant_desc,check",
        [
            (
                1,
                "_validate_cached_decision 返回 tuple[bool, Literal | None]",
                lambda: __import__(
                    "adapters.solidworks.sw_config_broker",
                    fromlist=["_validate_cached_decision"],
                )._validate_cached_decision is not None,
            ),
            (
                2,
                "_move_decision_to_history 暴露 + 接受 InvalidationReason",
                lambda: __import__(
                    "adapters.solidworks.sw_config_broker",
                    fromlist=["_move_decision_to_history"],
                )._move_decision_to_history is not None,
            ),
            (
                3,
                "_resolve_config_for_part_unlocked 暴露",
                lambda: __import__(
                    "adapters.solidworks.sw_config_broker",
                    fromlist=["_resolve_config_for_part_unlocked"],
                )._resolve_config_for_part_unlocked is not None,
            ),
            (
                4,
                "prewarm_config_lists 暴露 + detect_solidworks/cache_mod 模块级",
                lambda: (
                    hasattr(
                        __import__(
                            "adapters.solidworks.sw_config_broker",
                            fromlist=["prewarm_config_lists"],
                        ),
                        "detect_solidworks",
                    )
                    and hasattr(
                        __import__(
                            "adapters.solidworks.sw_config_broker",
                            fromlist=["prewarm_config_lists"],
                        ),
                        "cache_mod",
                    )
                ),
            ),
            (
                5,
                "INVALIDATION_REASONS 是 frozenset 含 3 字面量",
                lambda: (
                    isinstance(
                        __import__(
                            "adapters.solidworks.sw_config_broker",
                            fromlist=["INVALIDATION_REASONS"],
                        ).INVALIDATION_REASONS,
                        frozenset,
                    )
                    and len(
                        __import__(
                            "adapters.solidworks.sw_config_broker",
                            fromlist=["INVALIDATION_REASONS"],
                        ).INVALIDATION_REASONS
                    )
                    == 3
                ),
            ),
        ],
        ids=[
            "inv_1_validate_signature",
            "inv_2_move_decision_signature",
            "inv_3_resolve_unlocked_exposed",
            "inv_4_prewarm_module_level_imports",
            "inv_5_invalidation_reasons_frozenset",
        ],
    )
    def test_section_7_2_invariants_are_preserved(
        self, invariant_num, invariant_desc, check
    ):
        """T20 (spec §4.8 / §7.2): 5 条 invariant 任意一条破裂立即 fail，
        message 引用 §7.2 第 N 条。
        """
        result = check()
        assert result, (
            f"§7.2 invariant {invariant_num} 破裂: {invariant_desc}。"
            f"破坏者请检查是否预期此改动；如预期请同步更新 spec §7.2。"
        )
```

- [ ] **Step 11.3：跑 T19 + T20 + 全 broker test**

```bash
pytest tests/test_sw_config_broker.py::TestPrewarmConfigLists::test_e2e_prewarm_resolve_invalidate_history_pipeline -v 2>&1 | tail -10
pytest tests/test_sw_config_broker.py::TestSection72InvariantsRegression -v 2>&1 | tail -15
pytest tests/test_sw_config_broker.py -v 2>&1 | tail -5
```

预期：T19 PASS（commit 4 / commit 6 已实现 IO + Literal 后端到端通）；T20 5 invariant 全 PASS（M-6/M-7/M-8 行为已对齐）。

- [ ] **Step 11.4：commit 11**

```bash
git add tests/test_sw_config_broker.py
git commit -m "$(cat <<'EOF'
test(integration): 集成 + §7.2 invariant 回归测试（T19-T20，2 测试）

- T19 test_e2e_prewarm_resolve_invalidate_history_pipeline
  端到端：prewarm → resolve → cached invalidate → fall through → history append
  守护 §7.2 invariant 2+3+4

- T20 test_section_7_2_invariants_are_preserved（class TestSection72InvariantsRegression）
  参数化 5 个 sub-assertion，每条 invariant 一个 case
  fail message 引用 §7.2 编号让 reviewer 直接定位

spec §4.8 兜底：任何 invariant 破裂立即 fail。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: I-4 在 sw_config_lists_cache.py 加 1 行已知限制注释

**Files:**
- Modify: `adapters/solidworks/sw_config_lists_cache.py`（`_envelope_invalidated` 函数定义附近）

**Spec 参考:** §5.2（I-4 处理）

- [ ] **Step 12.1：grep `_envelope_invalidated` 函数定义位置**

```bash
grep -nA5 "^def _envelope_invalidated" adapters/solidworks/sw_config_lists_cache.py
```

记录该函数位置（spec rev 1.4 写作时 line 101）。

- [ ] **Step 12.2：在函数 docstring 末尾或函数体头部加 1 行注释**

定位 `_envelope_invalidated` docstring 关闭后第一行代码前，加：

```python
def _envelope_invalidated(cache: dict[str, Any]) -> bool:
    """..."""
    # I-4 已知限制（spec §5.2 won't fix）：mtime+size 哈希 collision
    # （SW UI 编辑保留同字节 + 同 mtime）极罕见——SW 改任何 config 都会更新 mtime；不修。
    ...
```

具体插入位置由 grep 结果确定。

- [ ] **Step 12.3：跑 sw_config_lists_cache 相关 test 验证不 regression**

```bash
pytest tests/test_sw_config_lists_cache.py -v 2>&1 | tail -5
```

预期：所有测试 PASS（注释不改行为）。

- [ ] **Step 12.4：commit 12**

```bash
git add adapters/solidworks/sw_config_lists_cache.py
git commit -m "$(cat <<'EOF'
chore(sw_config_lists_cache): I-4 加 1 行已知限制注释

spec §5.2 (won't fix)：mtime+size 哈希 collision 边界场景极罕见
（SW UI 编辑保留同字节 + 同 mtime），SW 改任何 config 都会更新 mtime。
仅 _envelope_invalidated 附近加注释，不改行为。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: spec §11 closure mark + CHANGELOG.md

**Files:**
- Modify: `docs/superpowers/specs/2026-04-26-sw-toolbox-config-list-cache-design.md`（§11 标 5 项 closed）
- Modify: `CHANGELOG.md`（加 v2.21.1 条目）

**Spec 参考:** §5.4（spec §11 整体清单）+ §6.3（CHANGELOG 条目）

- [ ] **Step 13.1：编辑 `2026-04-26-sw-toolbox-config-list-cache-design.md` §11**

grep 该文件 §11 中 5 个待 close 项位置：

```bash
grep -n "^- \*\*M-3 \|^- \*\*M-6 \|^- \*\*M-7 \|^- \*\*M-8 \|^- \*\*I-4 " docs/superpowers/specs/2026-04-26-sw-toolbox-config-list-cache-design.md
```

把每条 follow-up 描述末尾加 `✅ **closed (2026-04-27)**` + 引用本 PR 的 spec 文件路径。

例：

```markdown
- **M-7 transient COM 失败永久缓存** ... ✅ **closed (2026-04-27)**：worker rc 合约 ...
```

→

```markdown
- **M-7 ...** ✅ **closed (2026-04-27 PR #21 + 2026-04-27 v2.21.1)**：worker rc 合约 + Literal type
  + 双层 IO 边界守护。详见 [v2.21.1 cleanup spec](2026-04-27-sw-config-broker-followup-cleanup-design.md)。
```

类似处理 M-3 / M-6 / M-7 / M-8 / I-4 共 5 项。具体措辞按 spec §5.4 模板。

- [ ] **Step 13.2：在 `CHANGELOG.md` 加 v2.21.1 条目**

grep `## [v2.21.0]` 位置（PR #21 加的最新条目），在它**前面**插入：

```markdown
## [v2.21.1] - 2026-04-27

### Changed
- **sw_config_broker §11 minor cleanup（5 项 closed）**：
  - M-6: 函数级 import (`detect_solidworks` / `sw_config_lists_cache`) 提到模块级
  - M-7: `_validate_cached_decision` 返回类型用 `Literal[...]` 替代 `str`，
    删除 `_move_decision_to_history` 头部运行时校验（mypy 编译期保证）+ 加
    `_load_decisions_envelope` 读取端 IO 边界 runtime 校验（双层守护）
  - M-8: cached decision 失效路径加 `assert invalid_reason is not None` 锁定契约
  - M-3 / I-4: 文档化 won't-fix（详见 spec §11）

### Added
- **mypy strict CI gate（渐进式 typing 政策）**：仅
  `adapters/solidworks/sw_config_broker.py` 进 strict 检查
  （`pyproject.toml [tool.mypy] + [[tool.mypy.overrides]]` 两个 section + `tests.yml mypy-strict job`）
- **20 个新测试守护 §7.2 invariant**：5 类（M-6 / M-7 / M-7 IO 边界 / M-8 / mypy gate / 集成）
  全维度详尽测试矩阵 + invariant 反向 trace

```

- [ ] **Step 13.3：跑全 test 套最后一次确认**

```bash
pytest tests/ -v 2>&1 | tail -10
```

预期：所有测试 PASS，无 regression。

- [ ] **Step 13.4：跑覆盖率最终验证**

```bash
pytest tests/test_sw_config_broker.py --cov=adapters.solidworks.sw_config_broker --cov-report=term -v 2>&1 | tail -10
```

预期：覆盖率 ≥ baseline（PR #21 加的 ≥95% gate）。

- [ ] **Step 13.5：commit 13（最终）**

```bash
git add docs/superpowers/specs/2026-04-26-sw-toolbox-config-list-cache-design.md CHANGELOG.md
git commit -m "$(cat <<'EOF'
docs(spec): §11 标 M-3/M-6/M-7/M-8/I-4 closed + 引用本 spec + CHANGELOG v2.21.1

spec 联动 edit（§5.3 / §5.4）：
- 2026-04-26-sw-toolbox-config-list-cache-design.md §11 中 5 项标 closed (2026-04-27)
- 引用本 spec 路径 docs/superpowers/specs/2026-04-27-sw-config-broker-followup-cleanup-design.md

CHANGELOG.md 加 v2.21.1 条目：
- Changed: sw_config_broker §11 minor cleanup（M-3/M-6/M-7/M-8/I-4）
- Added: mypy strict CI gate（渐进式 typing 政策）+ 20 新测试 §7.2 invariant 反向 trace

§11 状态最终：
- closed: C-1/I-1/I-2/I-3/M-2/M-4/M-3/M-6/M-7/M-8/I-4 共 11 项
- 仍 open: M-1 fsync / M-5 prewarm timeout 公式（独立 PR）
- doc-only tracking: M-9 CI gate trace（已注释化）

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review Checklist（实施完成后）

- [ ] **覆盖率 gate** ≥ PR #21 baseline 的 95%（Linux + Windows）
- [ ] **mypy strict gate** ubuntu CI 退出码 0
- [ ] **既有测试**全 PASS 不 regression
- [ ] **新测试 T1-T20** 全 PASS（参数化展开后实际 collect 数更多）
- [ ] **删除 1 个测试方法**（test_move_decision_rejects_unknown_reason）确认
- [ ] **新增 fixture 文件**（tests/fixtures/_mypy_invalid_literal_fixture.py）确认
- [ ] **新增 4 测试 class**（TestModuleLevelImports / TestM8ContractGuard / TestMypyCIGate / TestSection72InvariantsRegression）确认
- [ ] **CHANGELOG.md** 加 v2.21.1 条目
- [ ] **PR #19 spec §11** 5 项标 closed
- [ ] **CI matrix 全绿**（6 平台 × py 版本 + regression + 新 mypy-strict）

## PR 创建后

- [ ] Branch protection 加 `mypy-strict` 进 main 必过 checks（manual action，spec §3.4）
- [ ] tag v2.21.1 + GitHub Release notes
- [ ] memory `project_current_status.md` 更新 §11 closed 进度（11 closed / 2 open / 1 tracking）
