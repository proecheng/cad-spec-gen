# sw_config_broker I-2 + I-3 修复设计

**日期：** 2026-04-26
**目标：** 修复 PR #19 self-review 推迟到 §11 follow-up 的 I-3（msvcrt 锁无重试 UX 损害"照片级"原则）+ I-2（envelope 升级未持久化导致死循环 invalidate），合并为单 PR 落地。
**关联 PR：** #19（v2.19.0 已 merge）的 review followup
**关联 spec：** `docs/superpowers/specs/2026-04-26-sw-toolbox-config-list-cache-design.md` §11
**北极星 gate 命中：** 结果准确（照片级图像质量）+ 傻瓜式（不弹 raw stack trace + 不诱导用户误删锁文件）

---

## §1 背景与问题

### §1.1 I-3 — msvcrt 锁无重试 UX

`adapters/solidworks/sw_config_broker.py:633-663` 的 `_project_file_lock` 守护项目级锁文件 `<project>/.cad-spec-gen/lock`，包住 `resolve_config_for_part` 防止两个 codegen 实例同时改 `spec_decisions.json`。当前用 `msvcrt.locking(fp.fileno(), msvcrt.LK_LOCK, 1)` 阻塞模式 — Windows 内核内置 ~10s 自动 retry，超时抛 raw `OSError`。

**问题**：
1. 用户撞锁时看到的是 Python `OSError` stack trace（违反"傻瓜式"gate）
2. 没有进度反馈，用户感受是"卡死"
3. 没有 Ctrl+C 友好提示路径

### §1.2 I-2 — envelope 升级未持久化

`prewarm_config_lists`（line 538-615）在检测到 `_envelope_invalidated == True`（SW 升级或 Toolbox 路径变）时，**仅在内存中**升级 sw_version + toolbox_path，要等 worker spawn 成功填 entries 后才一次性落盘（line 612）。

**问题**：worker 失败的所有早返路径（rc≠0 / TimeoutExpired / OSError / JSONDecodeError）都让"envelope 升级"决策**只活在内存**，下次 prewarm 进来读盘还是旧 envelope → 又判 invalidate → 又升级 → 又 spawn → 死循环重复。

### §1.3 严重度评估

| 维度 | I-3 | I-2 |
|------|-----|-----|
| 用户面伤害 | ✅ 直接 — 撞锁外行用户看到 raw OSError | ❌ 弱 — 性能浪费 + log 噪音，BOM loop 通过 fallback 仍能拿结果 |
| 北极星 gate 命中 | 傻瓜式 / 结果准确（防止用户误删锁文件造成 cache 数据竞争 → SW 件 mismatch → 图像非照片级）| 无直接命中（性能优化层）|
| 修复成本 | 中（~30 行重写）| 极低（1 行 + 2 行注释 + try/except 包）|
| 合并 PR 理由 | 自身就值得专 PR | 顺手（同文件 / review 上下文重叠）|

---

## §2 范围与改动概览

### §2.1 改动文件（仅 1 个）

`adapters/solidworks/sw_config_broker.py`

I-2 + I-3 都局限在这个文件，不波及 `sw_config_lists_cache.py`、`sw_list_configs_worker.py`、`sw_toolbox_adapter.py`、`parts_resolver.py`、`gen_std_parts.py`。

### §2.2 改动函数（仅 2 个）

- **`_project_file_lock`**（line 633-663） — I-3 修复点。函数体重写，签名 / 调用方不变。
- **`prewarm_config_lists`**（line 538-615） — I-2 修复点。`_envelope_invalidated` 分支末尾插一个 try/except 包的 save 调用。

### §2.3 不改动的"血管"

- `resolve_config_for_part`（主入口）签名不变 → caller `sw_toolbox_adapter` 不必动
- `_list_configs_via_com`（reader 路径）不变 → fallback 单件 spawn 行为保持
- `_save_config_lists_cache` / `_load_config_lists_cache` / `_envelope_invalidated` / `_config_list_entry_valid` 不变 → cache 模块完全 untouched
- `_save_decisions_envelope`（spec_decisions.json 写入）不变 → spec §6 既有契约保持

### §2.4 范围缩进表

| 维度 | 数量 |
|------|------|
| 改动文件 | 1 |
| 改动函数 | 2 |
| 既有测试改动 | 0 |
| 新增测试 | 32（详见 §6）|
| 新增 import | 1（`time` 模块顶部 import）|
| 新增模块级常量 | 2（`LOCK_POLL_INTERVAL_SEC` / `LOCK_PROGRESS_INTERVAL_SEC`）|
| 新增模块级文案常量 | 1（`_LOCK_WAITING_BANNER`）|
| commit 数 | 2（I-2 一个 + I-3 一个，便于 bisect）|

---

## §3 I-3 锁等待行为契约

### §3.1 重写后的 `_project_file_lock` 完整实现

```python
@contextlib.contextmanager
def _project_file_lock() -> Iterator[None]:
    """文件锁 <project>/.cad-spec-gen/lock（spec §6 + PR #19 review I-3）。

    Windows: msvcrt.LK_NBLCK 非阻塞 + 永不超时 polling + 撞锁立即提示 + 每 5s 进度
    非 Windows: 静默 yield（CI Linux 单元测试不依赖真并发）

    永不超时的理由：Windows msvcrt 锁 handle 与进程严格绑定，对方进程死必释放，
    不存在 stale lock。让用户用 Ctrl+C 主动控制，避免自动 hard fail 后引诱用户
    手动删锁文件造成 cache 数据竞争（损坏 spec_decisions.json → 下次跑用错配置 →
    SW 件 mismatch → 图像非照片级）。
    """
    if sys.platform != "win32":
        yield
        return

    import msvcrt
    from cad_paths import PROJECT_ROOT

    lock_path = Path(PROJECT_ROOT) / ".cad-spec-gen" / LOCK_FILE_NAME
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    fp = lock_path.open("a+b")
    try:
        wait_started_at = time.monotonic()
        last_progress_at = 0.0
        first_attempt = True
        while True:
            try:
                msvcrt.locking(fp.fileno(), msvcrt.LK_NBLCK, 1)
                break  # 拿到锁
            except OSError:
                now = time.monotonic()
                elapsed = now - wait_started_at
                if first_attempt:
                    print(
                        _LOCK_WAITING_BANNER.format(path=lock_path),
                        file=sys.stderr,
                        flush=True,
                    )
                    first_attempt = False
                    last_progress_at = now
                elif now - last_progress_at >= LOCK_PROGRESS_INTERVAL_SEC:
                    print(
                        f"⏳ 仍在等待锁释放...（已等 {int(elapsed)}s）",
                        file=sys.stderr,
                        flush=True,
                    )
                    last_progress_at = now
                time.sleep(LOCK_POLL_INTERVAL_SEC)

        try:
            yield
        finally:
            try:
                msvcrt.locking(fp.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError as e:
                log.warning("msvcrt unlock 异常（忽略）: %s", e)
    finally:
        fp.close()
```

### §3.2 模块级常量与文案

文件顶部 imports 区追加 `import time`（标准库）。

文件中部新增（与既有 `LOCK_FILE_NAME` 同段）：

```python
# I-3 锁等待行为参数（PR #19 review fix）
LOCK_POLL_INTERVAL_SEC = 0.5        # 每次 LK_NBLCK 失败后 sleep
LOCK_PROGRESS_INTERVAL_SEC = 5      # 进度提示间隔（首次立刻，之后每 5s）

_LOCK_WAITING_BANNER = (
    "⏳ 检测到另一个 codegen 实例正占用项目锁 ({path})，正在排队等待。\n"
    "   - 想中止：按 Ctrl+C\n"
    "   - 不要手动删除锁文件：与运行中实例并发改 cache 会损坏决策记录，\n"
    "     导致下次跑用错的 SW 配置（图像与 BOM 不一致）"
)
```

### §3.3 用户面行为矩阵

| 场景 | 用户感受 |
|------|----------|
| 没撞锁（99% case，cache hit fast-path）| 0 提示，毫秒级返回，无感 |
| 撞锁瞬间 | 立刻 1 行 banner（含 lock_path / Ctrl+C 提示 / 勿删锁文件警告）|
| 撞锁持续 | 每 5s 1 行进度（"已等 Ns"）|
| 用户主动中止 | Ctrl+C → KeyboardInterrupt 自然上抛，caller 默认 exit 130 |
| 对方释放 | 立刻拿到锁继续跑，无额外提示 |

### §3.4 永不超时的设计抉择

**否决方案：30s hard fail + "建议删锁文件"兜底文案**

理由：
1. Windows msvcrt 锁 handle 与进程严格绑定（Microsoft 文档承诺），对方进程死必释放，**真卡死场景不存在**；30s hard fail 实际只在"对方进程还活着但跑慢"时触发
2. 急切用户撞 hard fail 后会去手动删锁文件 → 与持锁 holder 并发改 `spec_decisions.json` / `sw_config_lists.json` → cache 被 partial overwrite → 下次 codegen 用错的 config → SW 件 mismatch → **图像非照片级**
3. 永不超时 + 用户 Ctrl+C 主导 = 用户能看到进度持续推进 + 想中止用 Ctrl+C 主动控制 + 不会出现"自动 fail 后强行删锁"反模式

worst case 计算：50 件 BOM 全 cold = 50 × ~5s = ~4 分钟。第二个进程跟随 holder 完成后立刻拿到锁。永不超时下用户最长等 ~4 分钟（且全程有进度反馈）—— 比 30s fail-then-retry-then-fail 循环更优。

### §3.5 已声明前提与边界

本节显式列出本设计依赖的前提，避免 plan 阶段实施者误读：

1. **Windows-only 产品范围**：用户 memory `user_windows_only_scope.md` 拍板"只支持 Windows 用户"；非 Windows 平台 `_project_file_lock` 退化为 `yield`（既有行为不变）→ 并发安全在 Linux/macOS 上**无保护**，但产品不支持非 Windows 故 acceptable
2. **Ctrl+C 残留 lock 文件无害**：用户 Ctrl+C 中断时 finally 块执行 `fp.close()` 但不删 lock 文件；多次中止累积的 lock 文件每个 ≤ 1 字节，无害（msvcrt advisory lock 重新获取无需文件清空）
3. **Ctrl+C signal 路径假设终端用户直接跑 codegen**：Windows 上 Ctrl+C → `CTRL_C_EVENT` → Python `KeyboardInterrupt`；CI subprocess 链 / PowerShell pipeline 中 Ctrl+C 行为不保证（parent 可能吞 signal）。本契约面向终端用户直接跑 codegen 场景，CI 测试通过 mock 验证逻辑，不依赖真 signal 传递

---

## §4 I-2 envelope 持久化语义

### §4.1 修改后的 `prewarm_config_lists`（仅高亮改动）

```python
def prewarm_config_lists(sldprt_list: list[str]) -> None:
    """fire-and-forget 预热持久化 cache（spec §3.1 + PR #19 review I-2）。"""
    if os.environ.get("CAD_SW_BROKER_DISABLE") == "1":
        return

    from adapters.solidworks import sw_config_lists_cache as cache_mod
    from adapters.solidworks.sw_detect import detect_solidworks

    cache = cache_mod._load_config_lists_cache()
    if cache_mod._envelope_invalidated(cache):
        log.info("config_lists envelope invalidated → 全 entries 清空重列")
        cache = cache_mod._empty_config_lists_cache()
        info = detect_solidworks()
        cache["sw_version"] = info.version_year
        cache["toolbox_path"] = info.toolbox_dir
        # ━━ I-2 修复插入位置：既有代码 line 565 `cache["toolbox_path"] = info.toolbox_dir`
        # 之后立即插入下面 try/except；既有代码 line 567 `miss = [...]` 之前。 ━━
        # I-2 修复：envelope 升级决策立即落盘，不依赖后续 worker 成功
        # 防"worker 失败 → 内存 envelope 丢 → 下次 prewarm 又重检测 invalidate"循环
        try:
            cache_mod._save_config_lists_cache(cache)
        except Exception as e:
            # save 失败不阻断 prewarm（fire-and-forget 契约：BOM loop 必须能拿到结果）
            # 用 except Exception 而非 except OSError：cache_mod 内部 bug（KeyError /
            # AttributeError 等）也应该 warn 而非 abort 整个 codegen；BaseException 子类
            # （KeyboardInterrupt / SystemExit）天然不被 catch，仍上抛保证 Ctrl+C 立即生效。
            log.warning(
                "config_lists envelope save 失败 (%s)；下次 prewarm 仍会重检测 invalidate",
                e,
            )

    # 后续 miss check / worker spawn / fill entries / save 全部不变
```

**改动总量**：try/except 5 行 + 调用 1 行 + 注释 2 行 = **8 行**。

### §4.2 落盘时机不变量

I-2 修完后，`~/.cad-spec-gen/sw_config_lists.json` 在以下时机会被写：

| 时机 | 触发条件 | 写入内容 |
|------|----------|----------|
| **A. envelope 升级**（**新增**）| `_envelope_invalidated == True` | 新 sw_version + 新 toolbox_path + 空 entries |
| B. entries 填充成功 | worker batch rc=0 + 解析成功 | 上面 + 填充的 entries |
| C. entries 填充全失败 | worker rc≠0 / TimeoutExpired / OSError / JSONDecodeError | **不再额外写**（A 已写过空 envelope，磁盘已是新状态）|
| D. entries 部分失败 | worker rc=0 但某些 entry 文件被删 | 同 B（部分填充 → save 一次）|

**核心 invariant**：磁盘 sw_version + toolbox_path 永远反映**最近一次 prewarm 见到的**真实 SW/Toolbox 状态，与 worker 输出无关。

### §4.3 与 worker 失败的交互（修复后行为对比）

**场景：用户升级 SW 2024 → 2025，第一次 prewarm 时 worker spawn 失败**

| 阶段 | 修复前 | 修复后 |
|------|--------|--------|
| 第一次 prewarm 进入 | 读盘旧 envelope (sw=2024) → invalidated → 内存升级到 2025 → spawn fail → return（**内存丢**）| 读盘旧 (sw=2024) → invalidated → 内存升级到 2025 → **save 落盘 (sw=2025, entries={})** → spawn fail → return |
| 第一次 BOM loop | reader 走 fallback 单件 spawn（每件单独跑 worker，仍可能拿到 configs）| 同左（fallback 行为不变）|
| 第二次 prewarm 进入 | 读盘还是 (sw=2024) → invalidated 又 True → 又升级又 spawn → 死循环 | 读盘 **(sw=2025, entries={})** → invalidated False → miss=sldprt_list 全集 → spawn 重试上次失败的件 |
| 后续 BOM loop | 同第一次（每次都浪费 1 次 batch worker）| worker 重试成功后 entries 填充，下次 prewarm 命中 cache fast-path |

### §4.4 与 I-3 的交互：无

`prewarm_config_lists` **不进 `_project_file_lock`** — prewarm 写的是用户级 `~/.cad-spec-gen/sw_config_lists.json`，项目锁守的是项目级 `<project>/.cad-spec-gen/`。两个修复完全正交，可独立 commit/review。

---

## §5 错误处理路径

### §5.1 I-3 错误路径表

| 异常源 | 处理 | 是否冒到 caller |
|--------|------|----------------|
| `msvcrt.locking(..., LK_NBLCK, 1)` 失败 | catch OSError → 进度提示 → retry | ❌ 内部消化 |
| `KeyboardInterrupt`（Ctrl+C 退出循环）| 不 catch → 自然上抛 | ✅ 上抛 |
| `lock_path.open("a+b")` 失败 | 不 catch → 自然上抛 | ✅ 既有行为不变 |
| `lock_path.parent.mkdir` 失败 | 不 catch → 自然上抛 | ✅ 既有行为不变 |
| `LK_UNLCK` 失败 | catch OSError + log.warning 忽略 | ❌ 既有行为不变 |
| `LK_UNLCK` 抛非 OSError | 不 catch → 自然上抛 | ✅ 异常类型严格性 |

**关键不变量**：用户 Ctrl+C 必须能立即中止。`time.sleep(0.5)` 是中断点，KeyboardInterrupt 在 sleep 内立即触发。

### §5.2 I-2 错误路径表

| 异常源 | 处理 | 是否冒到 caller |
|--------|------|----------------|
| **新增的 envelope 升级 `_save_config_lists_cache` 抛任何 `Exception` 子类**（含 OSError / RuntimeError / KeyError 等）| catch Exception + log.warning + 继续走 worker spawn | ❌ 内部消化（fire-and-forget 契约）|
| 新增 save 抛 `BaseException` 子类（KeyboardInterrupt / SystemExit / GeneratorExit）| `except Exception` 天然不 catch → 自然上抛 | ✅ 上抛（保证 Ctrl+C 立即生效）|
| `detect_solidworks()` 抛已知异常类型（OSError / ImportError / FileNotFoundError）| detect 内部已 catch 返 SwInfo(installed=False)（参见 `sw_detect.py` 多处 try/except）| ❌ 既有行为不变 |
| `detect_solidworks()` 抛 RuntimeError 等编程错误 | detect 内部**不** catch → 自然上抛（既有行为不变；新 try/except 仅包 `_save_config_lists_cache` 一行，**不**包 detect 调用）| ✅ 上抛（暴露真实编程错误）|
| 既有 line 612 的 `_save_config_lists_cache` | 既有 try/except 已包 | ❌ 既有行为不变 |

### §5.3 设计 invariant

1. **prewarm 永远不阻断 BOM loop（fire-and-forget 契约）**：任何 `Exception` 子类的 prewarm 内部错误（save 失败 / worker 失败 / detect 失败 / cache_mod 内部 bug 等）都 log.warning 静默；BOM loop 通过 reader 单件 fallback 路径仍能拿到 configs → 不影响图像质量。**例外**：`BaseException` 子类（KeyboardInterrupt / SystemExit）必须自然上抛，保证 Ctrl+C 立即生效
2. **resolve_config_for_part 锁等待可被用户中止**：Ctrl+C 立即生效；不静默兜底（不会自动切 CadQuery 损失图像准确性）
3. **decision data 写入失败必须 fail loud**：既有 `_save_decisions_envelope`（spec_decisions.json，**不是** sw_config_lists.json）失败应该上抛 — 这是 spec §6 现有承诺，本 PR 不动
4. **跨平台并发安全 = Windows-only**：Windows 上 `msvcrt.locking` 提供进程间互斥；非 Windows 上 `_project_file_lock` 是 noop（产品 Windows-only 范围内 acceptable，参见 §3.5）

### §5.4 "照片级 > 傻瓜式" 原则映射

| 决策 | 原则应用 |
|------|----------|
| I-3 永不超时 + 用户 Ctrl+C 主导 | 不让程序自动放弃 → 用户拿到真 SW 结果 → 照片级 |
| I-3 不建议删锁文件 | 防止 cache 数据竞争 → 防止用错配置 → 照片级 |
| I-2 save 失败 warn + 继续 | prewarm 是性能优化不影响图像；cache 写不进盘 BOM loop 仍走 fallback；阻断会让用户**拿不到任何结果** > 让用户拿到稍慢的真结果 |
| I-2 用 log.warning 通知 envelope save 失败 | save 升级失败是配置问题信号，log.warning 让 ops 能 grep 到 — 但不 hard fail（fire-and-forget 语义优先于 fail-loud）|

---

## §6 测试覆盖矩阵（32 测试详尽版）

测试设计哲学：**按行为维度系统化覆盖**，不只是"快乐路径 + 边角各 1 个"。每个维度独立维护一类回归 — 未来重构 broker.py 时若任一维度行为破坏，至少 1 测试 fail 定位到具体维度。

### §6.1 I-3 测试矩阵（18 测试 / 8 维度）

#### D1. happy path（2 测试）

| # | 测试名 | 验证目标 |
|---|--------|----------|
| T1 | `test_lock_yields_immediately_when_uncontended` | LK_NBLCK 第 1 次成功 → 0 banner / 0 进度 / yield 正常 / unlock 调用 1 次 |
| T2 | `test_lock_yield_body_exception_still_releases_lock` | yield body 抛 ValueError → 异常上抛 + unlock 仍调用 + fp.close() 仍调用 |

#### D2. 进度提示节奏（4 测试）

| # | 测试名 | 验证目标 |
|---|--------|----------|
| T3 | `test_lock_banner_printed_immediately_on_first_contention` | 第 1 次 LK_NBLCK 抛 OSError → banner 立即印（不等 5s）|
| T4 | `test_lock_no_progress_when_acquired_within_5s` | 撞锁 3s 后拿到 → banner 印 1 次 + 进度行 0 行 |
| T5 | `test_lock_one_progress_at_5s_threshold` | 撞锁 6s 后拿到 → banner 1 + 进度行 1 行（含 "已等 6s"）|
| T6 | `test_lock_progress_intervals_strictly_5s` | 撞锁 16s 后拿到 → 进度行 3 行（5s/10s/15s）；4s/9s/14s 时刻**不**印 |

#### D3. 永不超时（2 测试）

| # | 测试名 | 验证目标 |
|---|--------|----------|
| T7 | `test_lock_never_raises_timeout_at_60s_and_sleeps_between_polls` | 撞锁 60s+ → 不抛 OSError；最终拿到锁仍正常 yield；**额外断言**：`time.sleep` 被调用次数 ≥ 100（防 CPU busy loop 死循环 — 实施者忘记 sleep 时此断言 fail）+ 每次 sleep 参数 == `LOCK_POLL_INTERVAL_SEC` 严格匹配（防间隔被改）|
| T8 | `test_lock_progress_count_matches_floor_elapsed_div_5` | 撞锁 27s 后拿到 → 进度行恰 5 行（5/10/15/20/25 时刻）|

#### D4. Ctrl+C 中止（2 测试）

| # | 测试名 | 验证目标 |
|---|--------|----------|
| T9 | `test_lock_keyboard_interrupt_during_sleep_propagates` | sleep 期间 raise KeyboardInterrupt → 立即上抛 + fp.close() 仍执行 + 不调 unlock |
| T10 | `test_lock_keyboard_interrupt_after_lk_nblck_fails_propagates` | LK_NBLCK 抛 OSError 后、进 sleep 前 raise KeyboardInterrupt → 立即上抛 + fp.close() |

#### D5. 清理路径（3 测试）

| # | 测试名 | 验证目标 |
|---|--------|----------|
| T11 | `test_lock_unlock_oserror_silently_warned` | unlock 抛 OSError → log.warning 触发 + 不冒到 caller |
| T12 | `test_lock_unlock_non_oserror_propagates` | unlock 抛 RuntimeError → 上抛（异常类型严格性，防"宽 except"）|
| T13 | `test_lock_path_with_chinese_chars_works` | lock_path 父目录路径含中文字符（如 `D:/工作/项目/.cad-spec-gen/`）→ open + locking + unlock 全程无 UnicodeError；Windows msvcrt 对 unicode 路径的支持回归 |

#### D6. 跨平台（2 测试）

| # | 测试名 | 验证目标 |
|---|--------|----------|
| T14 | `test_lock_noop_on_linux` | sys.platform = "linux" → 静默 yield + 无 msvcrt 调用 + 无 banner / 进度 |
| T15 | `test_lock_noop_on_darwin` | sys.platform = "darwin" → 同上 |

#### D7. 文案完整性（2 测试）

| # | 测试名 | 验证目标 |
|---|--------|----------|
| T16 | `test_lock_banner_contains_all_required_keywords` | banner stderr 包含全部 6 实体关键词组（精炼防文案微调误伤）：`codegen` / `占用` / `Ctrl+C` / `删除` / `配置` / `BOM`（不验完整句子，仅验关键 token 出现）|
| T17 | `test_lock_banner_contains_lock_file_path_literal` | banner 含 `lock_path` 字面字符串 |

#### D8. 输出 channel（1 测试）

| # | 测试名 | 验证目标 |
|---|--------|----------|
| T18 | `test_lock_banner_and_progress_only_on_stderr` | capsys.readouterr() — stdout 为空 / stderr 含 banner + 进度 |

### §6.2 I-2 测试矩阵（14 测试 / 7 维度）

#### E1. 核心顺序 invariant（2 测试）

| # | 测试名 | 验证目标 |
|---|--------|----------|
| T19 | `test_invalidate_save_called_before_worker_spawn` | call_order 列表断言：save(2025, entries={}) 出现在 subprocess.run(worker) 之前 |
| T20 | `test_invalidate_save_content_correct` | **测试前提**：mock 旧 cache `sw_version=2024 / toolbox_path="C:/old"`，mock detect 返新 `version_year=2025 / toolbox_dir="C:/new"`（值显式不同，防 mutation `cache.get("sw_version", info.version_year)` 偷换旧值后 T20 仍 pass）。save 调用时 cache dict 字面值：`schema_version=1 / sw_version=2025 / toolbox_path="C:/new" / entries={}` 严格匹配；`generated_at` 仅验存在 + 符合 ISO 8601 时间字符串格式（dynamic 值不字面匹配）|

#### E2. save 失败路径（3 测试）

| # | 测试名 | 验证目标 |
|---|--------|----------|
| T21 | `test_invalidate_save_oserror_warns_and_continues_to_worker` | mock save 抛 OSError → log.warning 触发（"envelope save 失败" 关键词）+ worker spawn 仍调用 + prewarm 不抛 |
| T22 | `test_invalidate_save_any_exception_warns_and_continues` | 用 `@pytest.mark.parametrize("exc_type", [RuntimeError, KeyError, TypeError, ValueError, AttributeError])` 5 种 Exception 子类各跑一遍：mock save 抛 `exc_type` → catch + log.warning（含"envelope save 失败"关键词）+ worker spawn 仍调用 + prewarm 不抛（fire-and-forget 契约）。防 mutation `except (OSError, RuntimeError)` 漏 KeyError 等 |
| T22b | `test_invalidate_save_baseexception_propagates` | mock save 抛 KeyboardInterrupt → `except Exception` 天然不 catch → 上抛 + worker spawn 不调用（保证 Ctrl+C 立即生效，BaseException 子类不被吞）|

#### E3. 第二次 prewarm 验证（2 测试）

| # | 测试名 | 验证目标 |
|---|--------|----------|
| T23 | `test_two_prewarm_calls_after_worker_fail_no_redundant_invalidate` | 第 1 次 prewarm worker fail → 第 2 次 prewarm 进入时 `_envelope_invalidated(cache) == False` + 不再走升级分支 |
| T24 | `test_two_prewarm_calls_after_worker_fail_retries_failed_sldprt` | 第 2 次 prewarm 走 miss diff → spawn worker 重试上次失败的 sldprt |

#### E4. detect 边角（2 测试）

| # | 测试名 | 验证目标 |
|---|--------|----------|
| T25 | `test_invalidate_save_when_sw_not_installed` | mock detect_solidworks 返 SwInfo(installed=False, version_year=0, toolbox_dir="") → 仍 save sw_version=0 / toolbox_path="" 到磁盘 |
| T26 | `test_invalidate_save_propagates_detect_unexpected_exception` | detect_solidworks 抛 RuntimeError → 上抛（detect 调用**不在** I-2 新 try/except 包围范围内 — 即使 except Exception 也只包 `_save_config_lists_cache` 一行；防实施者把 except 范围误扩到包整个 invalidate 分支）|

#### E5. 安全阀 regression（1 测试）

| # | 测试名 | 验证目标 |
|---|--------|----------|
| T27 | `test_prewarm_disable_env_skips_all_cache_ops` | `CAD_SW_BROKER_DISABLE=1` → 整函数早返；磁盘 cache 文件不被读 / 不被写 |

#### E6. 磁盘内容精确性（3 测试）

| # | 测试名 | 验证目标 |
|---|--------|----------|
| T28 | `test_invalidate_save_disk_json_schema_full_match` | save 后磁盘 JSON 反序列化 → 5 字段全员存在；schema_version=1 / sw_version=新 / toolbox_path=新 / entries={} 严格匹配；`generated_at` 仅验存在 + ISO 8601 格式（dynamic 值不字面匹配）|
| T29 | `test_invalidate_save_then_worker_success_disk_has_entries` | invalidate save → worker success → 第 2 次 save → 磁盘 JSON 含 entries{p1, p2}（验证两次 save 累积一致性）|
| T30 | `test_invalidate_save_does_not_overwrite_unrelated_user_files` | save 只写 `~/.cad-spec-gen/sw_config_lists.json`；同目录的 `sw_toolbox_index.json` / `decisions.json` 等不被 touched |

#### E7. 路径 gating（1 测试）

| # | 测试名 | 验证目标 |
|---|--------|----------|
| T31 | `test_no_invalidate_no_extra_envelope_save` | mock `_envelope_invalidated` 返 False（cache 已是新 envelope）→ call_order 中**不**出现 invalidate 分支 save；只有既有 worker spawn（如有 miss）+ 既有 line 612 save（如 worker 成功）→ 防实施者把新 save 写成无条件调用、漏在 `if _envelope_invalidated:` 分支外 |

### §6.3 Coverage 预算

#### 既有 baseline（PR #19 merge 后 main @ `959f893`）

| 环境 | passed | failed | skipped | errors | collection errors |
|------|--------|--------|---------|--------|------------------|
| 本地（部分可选依赖未装）| 1251 | 35 | 32 | 13 | 2 |
| CI（装全依赖）| 7/7 SUCCESS（具体数字以 GitHub Actions run 为准）| - | - | - | - |

**预存技术债说明**：本地的 35 failed + 13 errors + 2 collection errors 全部源于 `cadquery` / `partcad` / `bd_warehouse` 等可选依赖未装导致的 `ModuleNotFoundError`，**与本 PR 完全无关**。CI 配置装了全依赖故应为 0。

#### 修复后目标

- **新增 32 测试均不依赖 cadquery / partcad / bd_warehouse**（纯 `unittest.mock` + 标准库 + msvcrt mock）
- 修复后**本地**：1251 + 32 = **1283 passed**；其他数字（35 failed / 32 skipped / 13 errors / 2 collection errors）**0 增长**（即不破坏既有失败状态）
- 修复后 **CI**：7/7 全平台 SUCCESS 仍是 gate 标准

#### 验收命令

```bash
# 本地验收（绕过 cadquery 相关）
.venv/Scripts/python.exe -m pytest -q \
  --ignore=tests/test_a2_integration.py \
  --ignore=tests/test_part_templates.py \
  2>&1 | tail -3
# 期望: 1283 passed, ... 35 failed, 32 skipped, ... 13 errors

# CI 验收
gh pr view <PR#> --json statusCheckRollup -q '.statusCheckRollup[].conclusion' | sort -u
# 期望: SUCCESS（且仅 SUCCESS）
```

### §6.4 mock helper 设计指引（plan 阶段实施约束）

为了让 30+ 测试能稳定 catch 实施 bug 而非 mock bug，统一以下 mock 模式：

#### 时间相关 mock

`time.monotonic()` 必须**与 `time.sleep` 调用次数同步推进**，**不**用固定序列：

```python
# ✅ 正确：sleep 推进时钟
fake_now = [0.0]
def fake_sleep(seconds):
    fake_now[0] += seconds
def fake_monotonic():
    return fake_now[0]
monkeypatch.setattr(broker.time, "sleep", fake_sleep)
monkeypatch.setattr(broker.time, "monotonic", fake_monotonic)

# ❌ 错误：固定序列（会让"忘记 sleep"的 busy loop bug 测试照样过）
times = iter([0.0, 5.0, 10.0, 15.0, 16.0])
monkeypatch.setattr(broker.time, "monotonic", lambda: next(times))
```

理由：固定序列模式下实施者删掉 `time.sleep(...)` 调用，测试因为 `time.monotonic` 仍然按固定序列推进而误判通过。**真实部署会 100% CPU**，而测试看不出来。

#### `msvcrt` fake 模块构造（跨平台 universal — setitem 统一方案）

**关键事实**：项目 `tests/conftest.py` + `pyproject.toml` 仅注册 `requires_solidworks` marker，**不存在** `requires_windows` marker。本 PR **不**新增 file-level marker（避免与既有惯例冲突），改用 mock 让所有测试在 Linux CI / Windows local 都能跑。

```python
import sys
import types

def make_fake_msvcrt(locking_calls: list, contention_count: int = 0):
    """构造 fake msvcrt 模块，Linux 上没有真 msvcrt 也能用。

    使用 setitem(sys.modules, "msvcrt", ...) 注入：函数体内 `import msvcrt` 命中 fake。
    **不**用 setattr(real_msvcrt, ...) — Linux 上 real_msvcrt 不存在 import 即炸。
    """
    fake = types.ModuleType("msvcrt")
    fake.LK_NBLCK = 1
    fake.LK_UNLCK = 2
    fake.LK_LOCK = 3
    fake.LK_NBRLCK = 4

    def locking(fd, mode, nbytes):
        mode_name = "LK_NBLCK" if mode == fake.LK_NBLCK else "LK_UNLCK"
        locking_calls.append((mode_name, fd, nbytes))
        if mode == fake.LK_NBLCK and len(locking_calls) <= contention_count:
            raise OSError("contended")
        return None

    fake.locking = locking
    return fake
```

**测试中使用**：
```python
locking_calls = []
fake_msvcrt = make_fake_msvcrt(locking_calls, contention_count=10)
monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)
monkeypatch.setattr(sys, "platform", "win32")
# 之后调用 broker._project_file_lock() 时，函数体内 `import msvcrt` 命中 fake_msvcrt
```

#### `_save_config_lists_cache` mock — **双模板**

##### `tracking_save`（用于"成功路径"测试 T19 / T20 / T28 / T29 等）

call_order 列表用 `("save", sw_version, len(entries))` 元组记录，**不**用 `MagicMock.call_args_list`（mock 对 dict mutate 行为不友好，dict 共享引用易出错）：

```python
call_order = []
def tracking_save(cache):
    call_order.append(("save", cache.get("sw_version"), len(cache.get("entries", {}))))
    return real_save(cache)  # 真写盘以便磁盘验证测试（T28/T29）也能复用此 mock
monkeypatch.setattr(cache_mod, "_save_config_lists_cache", tracking_save)
```

##### `failing_save`（用于"失败路径"测试 T21 / T22 / T22b）

```python
def make_failing_save(exception_to_raise):
    """构造抛指定异常的 fake save，不真写盘。"""
    def failing_save(cache):
        raise exception_to_raise
    return failing_save

# T21 用：抛 OSError
monkeypatch.setattr(cache_mod, "_save_config_lists_cache",
                    make_failing_save(OSError("disk full")))

# T22 parametrize 用：每个 exc_type 调 make_failing_save(exc_type("test"))
@pytest.mark.parametrize("exc_type", [RuntimeError, KeyError, TypeError, ValueError, AttributeError])
def test_invalidate_save_any_exception_warns_and_continues(exc_type, ...):
    monkeypatch.setattr(cache_mod, "_save_config_lists_cache",
                        make_failing_save(exc_type("test")))

# T22b 用：抛 KeyboardInterrupt（BaseException 子类）
monkeypatch.setattr(cache_mod, "_save_config_lists_cache",
                    make_failing_save(KeyboardInterrupt()))
```

#### 跨平台测试策略（Linux CI + Windows local 都全跑通）

| 测试组 | sys.platform mock | msvcrt mock | 既有 marker |
|--------|-------------------|-------------|-------------|
| D1-D5/D7/D8 (T1-T13/T16-T18) Windows 行为 | `setattr(sys, "platform", "win32")` | `setitem(sys.modules, "msvcrt", fake)` | 无 |
| D6 (T14) Linux noop | `setattr(sys, "platform", "linux")` | 不需（Windows 早返路径不走 import msvcrt）| 无 |
| D6 (T15) macOS noop | `setattr(sys, "platform", "darwin")` | 不需 | 无 |
| E1-E7 (T19-T31 + T22b) I-2 测试 | 不需 mock platform（prewarm 跨平台都进函数体）| 不需（prewarm 不调 msvcrt）| 无 |

**所有测试都不依赖真平台**，CI matrix（Ubuntu / Windows / macOS）都能完整跑。这是与 memory `feedback_ci_windows_only_skipif.md` 既有 Pattern A/B 的区别：本 PR 用 mock 模式而非 skipif marker 模式，因 32 测试都设计为可 mock，无真平台依赖。

---

## §7 PR 结构与 commit 划分

### §7.1 commit 拆分（3 commits）

#### commit-test 编号 mapping 表

| commit | 内容 | 测试编号（与 §6 章节对应）| 测试数 |
|--------|------|--------------------------|-------|
| Commit 1（I-2 先做）| `prewarm_config_lists` 加 try/except + save | T19-T31 + T22b（§6.2 I-2 矩阵）| 14 |
| Commit 2（I-3 后做）| `_project_file_lock` 重写 + 常量 + 文案 + `import time` | T1-T18（§6.1 I-3 矩阵）| 18 |
| Commit 3（spec close）| 既有 cache-design spec §11 标 closed + 反向链接 | — | 0 |

> **mapping 注意**：测试编号 T1-T31 + T22b 按 §6.1 (I-3) → §6.2 (I-2) 章节顺序编排；但 commit 顺序 I-2 在前 I-3 在后，所以 commit 1 跑 T19-T31 + T22b（共 14），commit 2 跑 T1-T18（共 18）。**plan 阶段拆 task 时务必按 commit-test mapping 落地，不按编号自然顺序**。

#### commit 详细内容

**Commit 1（I-2 先做）**：`fix(sw_config_broker): I-2 envelope 升级立即落盘（PR #19 review fix）`
- 改 `prewarm_config_lists` invalidate 分支末尾加 try/except + save（§4.1 代码）
- 加 14 测试 T19-T31 + T22b（§6.2 I-2 矩阵）
- 通过 → push CI → 全绿

**Commit 2（I-3 后做）**：`fix(sw_config_broker): I-3 锁等待永不超时 + 进度提示（PR #19 review fix）`
- 重写 `_project_file_lock`（§3.1 代码）
- 加 18 测试 T1-T18（§6.1 I-3 矩阵）
- 加 2 常量 + 1 文案常量（§3.2）+ `import time` 顶部
- 通过 → push CI → 全绿

**Commit 3（spec close）**：`docs(spec): I-2 + I-3 close 在 §11 follow-up 标 closed`
- 改 `2026-04-26-sw-toolbox-config-list-cache-design.md` §11 把 I-2 / I-3 标 closed + 链接本 spec

I-2 先做的理由：改动 surgical（8 行），TDD 周期短，先稳一波 baseline；I-3 改动较大（30+ 行 + 18 测试），后做时已有干净 baseline 可对照。

### §7.2 PR 标题 / 描述

```
fix(sw_config_broker): I-2 + I-3 PR #19 review followup
```

PR 描述模板：
```markdown
## Summary
- I-2: envelope 升级决策立即持久化，避免 worker 失败导致死循环 invalidate
- I-3: 锁等待永不超时 + Ctrl+C 友好 + 文案防误删锁文件，对齐"照片级 > 傻瓜式"原则

## 关联
- spec: docs/superpowers/specs/2026-04-26-sw-config-broker-i2-i3-fix-design.md
- 跟进 PR #19 self-review §11 follow-up

## 测试
- 新增 32 测试（I-3: 18 / I-2: 14）按 15 个行为维度详尽覆盖
- 总 1281 passed (baseline 1251 + 30 new)
- CI 7/7 全平台绿
```

---

## §8 验收清单

### §8.1 功能验收
- [ ] I-3：撞锁 → 立即印 banner（含 4 关键词 + lock_path）+ 每 5s 进度 + 永不超时 + Ctrl+C 立即上抛
- [ ] I-3：unlock OSError 静默 / 非 OSError 上抛
- [ ] I-3：非 Windows 静默 yield
- [ ] I-2：envelope_invalidated → save 在 worker spawn 之前 → 第 2 次 prewarm 不再 invalidate
- [ ] I-2：save 失败 warn + 继续；非 OSError 异常上抛
- [ ] I-2：detect SW 未装时仍 save sw_version=0
- [ ] I-2：CAD_SW_BROKER_DISABLE=1 整函数早返

### §8.2 测试验收
- [ ] 30 新测试 100% pass
- [ ] 既有 1251 测试 0 regression
- [ ] CI 7/7 SUCCESS

### §8.3 代码质量验收
- [ ] mypy 严格模式无新增错误
- [ ] ruff lint + format pass
- [ ] 改动 surgical（仅 1 文件 + 2 函数 + 32 测试 + 1 import + 3 常量）
- [ ] 不破坏既有"血管"（resolve_config_for_part / reader / cache 模块 / sw_toolbox_adapter / parts_resolver / gen_std_parts）

### §8.4 文档验收
- [ ] 本 spec commit 入库
- [ ] PR #19 spec §11 标 I-2 / I-3 closed + 反向链接本 spec
- [ ] PR 描述完整含 summary / 关联 / 测试

---

## §9 实施顺序提示（给 plan 阶段参考）

1. **Task 0**：grep 验证当前实现（`msvcrt.locking` / `_envelope_invalidated` / `_save_config_lists_cache` 调用点准确性）
2. **Task 1**：I-2 修复（先做，surgical）
   - 1.1 写 14 测试 RED（T19-T31 + T22b）
   - 1.2 实现 8 行改动
   - 1.3 跑测试 GREEN
   - 1.4 commit + push CI
3. **Task 2**：I-3 修复（后做，较大）
   - 2.1 写 18 测试 RED（按 8 维度分批，每批 3-5 测试）
   - 2.2 实现 _project_file_lock 重写 + 常量 + 文案
   - 2.3 跑测试 GREEN
   - 2.4 commit + push CI
4. **Task 3**：spec §11 close + 本 spec 入库
   - 3.1 改既有 spec §11 标 closed
   - 3.2 commit
5. **Task 4**：开 PR + 等 CI 全绿 + merge

具体 plan 由 `superpowers:writing-plans` skill 展开成 5-8 个 Task 的 task-by-task 实施步骤。
