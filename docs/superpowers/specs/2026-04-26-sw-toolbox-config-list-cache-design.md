# SW Toolbox `_list_configs_via_com` 跨 run 持久化 cache 设计（Task 14.6 / P1）

**状态**：design pending plan
**作者**：Claude Opus 4.7（与用户 brainstorming 产出）
**日期**：2026-04-26
**前置 spec**：`docs/superpowers/specs/2026-04-25-sw-toolbox-llm-config-broker-design.md`（Task 14 系列）
**关联 plan**：待产出（writing-plans skill 下一步）

---

## §1 问题陈述

### 1.1 现状痛点

`adapters/solidworks/sw_config_broker.py` 当前的 `_list_configs_via_com` 通过 spawn `sw_list_configs_worker` subprocess 启动 SW COM 列出 SLDPRT 当前可用 configurations：

- `_CONFIG_LIST_CACHE: dict[str, list[str]]` 是模块级 in-process 缓存，**每个 Python 进程从空开始**
- `resolve_config_for_part` 第一行无条件调 `_list_configs_via_com`（broker.py:602）
- 每次 codegen 启动 → 每个 unique sldprt_path 启 1 次 SW

**实测影响**（GISBOT 项目）：
- BOM 54 个零件 = **54 次 spawn worker = 54 次启 SW**
- 每次启 SW 5-30 秒
- 整 codegen 多花 15+ 分钟纯启动开销
- 违反用户北极星 "装即用 / 傻瓜式" 硬约束

### 1.2 用户北极星硬约束（5 个 gate）

1. **零配置** — 不让用户手动 warmup 索引
2. **稳定可靠** — 断网/SW 装新版/Toolbox 路径变都不能崩
3. **装即用** — 用户装 SW Premium 后第一次 codegen 应该就快
4. **傻瓜式** — 不问用户 mtime 还是 hash，自动决策
5. **结果准确** — cache 不能给错 config_name 列表导致误匹配

### 1.3 成功判据

- 第一次 codegen（cache 全 miss）：**1 次 spawn worker** 列 BOM 全部用到的件（vs 现 N 次）
- 后续 codegen（cache 全命中）：**0 次 spawn worker**
- 增量失效（用户改 1 件 sldprt）：**1 次 spawn worker** 仅列变化件
- envelope 失效（SW 升级 / Toolbox 路径变）：**1 次 batch spawn** 重列 BOM 用到的件
- 所有失败模式（worker timeout / SW crash / cache 损坏）：退化到现有 per-part 单件 spawn 路径，**codegen 不崩**

---

## §2 设计决策（brainstorming 答案）

### Q1：复用边界 → **B**
新文件 `~/.cad-spec-gen/sw_config_lists.json`（用户级独立文件 + per-sldprt mtime/size 失效）。

**Why**：
- 用户级 cache 让"装 SW Premium 后任何项目第一次 codegen 都快"兑现 "装即用"
- 与已有 `sw_toolbox_index.json` (catalog SCHEMA_VERSION=1) 解耦——一个管 sldprt 元数据，一个管 SW COM 调用结果
- per-sldprt 失效让 SW 升级补丁/单件改不会全 cache 失效

**为什么不选 A（挂 toolbox_index.json）**：toolbox_fingerprint 是 SHA1(整个目录 sldprt mtime/size) → 任意一件改触发整 cache 重列；与 B 的 per-sldprt 失效精度不符。

**为什么不选 C（per-project broker spec_decisions）**：用户切项目时 cache 失效，违反"装即用"——新项目第一次 codegen 仍要 N 次 spawn。

### Q2：cache miss 时启 SW 几次 → **B**
Batch 一次 spawn 列全部 miss 的 sldprt。让 `sw_list_configs_worker` 接受 sldprt 列表（stdin JSON），broker 在 BOM loop 之前先 prewarm 阶段 collect → 一次 batch → 后续 loop 全 cache 命中。

**Why**：
- 第一次 codegen 1 次 spawn 处理 N 件 ≈ 1 分钟（vs A 的 5-25 分钟）—— 这是 "装即用" 的真正兑现
- 比 C（long-running worker IPC）实施复杂度低一档；C 的进程生命周期管理 + 异常恢复 + worker crash 自愈在"稳定可靠"红线上风险高

### Q3：哪些事件让 cache 失效 → **C**
**(mtime + size + SW 版本 + Toolbox 路径)** 四维。

**Why**：
- mtime 漏抓 NTFS 2s 精度问题 → size 兜底
- SW 升级（23→24）sldprt 内格式可能变 → 用 sw_version 整 envelope 失效保险
- Toolbox 路径变是用户大动作（重装/迁移） → 整 envelope 失效避免悄悄返错件
- false positive 代价（罕见事件）：~30-60s 重列 BOM 用到的件，可接受
- D 选项（content SHA1）的每次 codegen 启动 hash 1818 件 5-10s 是天天交学费，不值

### Implementation approach → **Approach 1（一次性全做）**

单次 plan 完成 envelope + worker + 调用链改造。**为何不分阶段**：Approach 2 中间状态用户体验是"第一次仍卡，第二次才快" —— 不达 "装即用" 北极星；Approach 3（仅持久化）直接放弃北极星。

---

## §3 架构

### 3.1 总体形状

```
gen_std_parts.main(spec)
 ├─ queries = [PartQuery(...) for p in bom]                       # main 现已 build PartQuery
 └─ resolver.prewarm(queries)                                     ← 新 API

# PartsResolver.prewarm 实现（关键：rule matching 在 resolver 层做，不在 adapter 层）：
#   for adapter in self.adapters:
#       candidates = []  # list[(PartQuery, dict)] 形如 [(query, rule.spec)]
#       for q in queries:
#           for rule in self.registry.get("mappings", []):
#               if not _match_rule(rule.get("match", {}), q): continue
#               if rule.get("adapter", "") != adapter.name: continue
#               candidates.append((q, rule.get("spec", {})))
#               break  # first-hit-wins，与 PartsResolver.resolve 一致
#       if not candidates: continue
#       try: adapter.prewarm(candidates)
#       except Exception as e: log.warning("prewarm 失败 %s: %s", adapter.name, e)
#       # prewarm 失败不阻 codegen：BOM loop 走原 fallback 路径

# sw_toolbox_adapter.prewarm(candidates) 实现：
#   collect = []
#   for query, spec in candidates:
#       sldprt = self.find_sldprt(query, spec)                    ← 已有 API（catalog-only，不调 COM）
#       if sldprt: collect.append(sldprt.sldprt_path)
#   if collect:
#       broker.prewarm_config_lists(collect)                      ← 新 public API

# broker.prewarm_config_lists 实现：
#   if os.getenv("CAD_SW_BROKER_DISABLE") == "1": return          # 复用安全阀（issue 9）
#   cache = _load_config_lists_cache()                            # 读 JSON，损坏视为空
#   if _envelope_invalidated(cache): cache = _empty_config_lists_cache()  # SW 版本 / Toolbox 路径变
#   miss = [sldprt for sldprt in collect if not _config_list_entry_valid(cache, sldprt)]
#   if not miss: return                                           # 全命中
#   try:
#       result = subprocess.run([worker, '--batch'],
#                               input=json.dumps(miss).encode(), timeout=180)
#       if result.returncode != 0: return                         # batch 失败 → 不动 cache
#       for entry in json.loads(result.stdout):
#           cache['entries'][entry['path']] = {
#               'mtime': _stat_mtime(entry['path']),
#               'size': _stat_size(entry['path']),
#               'configs': entry['configs'],
#           }
#       _save_config_lists_cache(cache)                           # atomic .tmp + os.replace
#   except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError):
#       return                                                    # 失败 → BOM loop 走单件 fallback

# BOM loop 内现有 broker.resolve_config_for_part 不变；
# _list_configs_via_com 改为三层：
#   1. in-process L2 (_CONFIG_LIST_CACHE) 命中 → return           # 现有
#   2. 持久化 L1 cache 命中 → 填 L2 → return                      ← 新增
#   3. fallback：单件 spawn worker（罕见兜底）                    # 现有
#      ⚠️ fallback 只填 L2 (in-process)，不写回 L1 持久化（issue 4）：
#         - 不写：下次 prewarm 自然修复（fallback 罕见，cost 低）
#         - 写：fallback 路径变复杂 + 并发竞争（不值）
```

### 3.2 6 个新/改组件

| 组件 | 类型 | 责任 | 文件 |
|---|---|---|---|
| `~/.cad-spec-gen/sw_config_lists.json` | 新数据文件 | 持久化 envelope (schema_version + sw_version + toolbox_path + entries[]) | 运行时产物 |
| `sw_config_lists_cache` (新 module) | **新 module** | envelope load/save/empty/diff/invalidation 全部归此；含 `CONFIG_LISTS_SCHEMA_VERSION = 1` 模块级常量（避免与 broker.SCHEMA_VERSION=2 / catalog.SCHEMA_VERSION=1 撞名） | `adapters/solidworks/sw_config_lists_cache.py` |
| `broker.prewarm_config_lists(sldprt_list)` | 新 public API | 调 cache module 的 _load → diff miss → spawn batch worker → 调 cache module 的 _save | `adapters/solidworks/sw_config_broker.py` |
| `PartsAdapter.prewarm(candidates)` | 新 virtual method | 基类 default no-op body（不是 abstractmethod，避免现有 4 adapter 加 pass 占位）；sw_toolbox 重写实现 | `adapters/parts/base.py` + `sw_toolbox_adapter.py` |
| `PartsResolver.prewarm(queries)` | 新 method | **rule matching 在此做** — 对每 query 跑 _match_rule，按 first-hit adapter 分组成 candidates → 派发；per-adapter try/except；返 `None` (fire-and-forget) | `parts_resolver.py` |
| `sw_list_configs_worker.py` | 改 IPC 协议 | 加 `--batch` + stdin JSON list 模式（保留单件 CLI 兼容） | `tools/sw_list_configs_worker.py` |

**变量命名约定**（避免与 broker / catalog 现有 helper 撞名）：
- 模块级常量：`CONFIG_LISTS_SCHEMA_VERSION = 1`
- helper 函数：`_load_config_lists_cache` / `_save_config_lists_cache` / `_empty_config_lists_cache` / `_config_list_entry_valid` / `_envelope_invalidated`
- 路径计算：`Path.home() / '.cad-spec-gen' / 'sw_config_lists.json'`（与 `sw_toolbox_index.json` 同模式 — catalog.py:70；不依赖 `cad_paths.PROJECT_ROOT`，因为本 cache 是用户级跨项目共享）

### 3.3 不动的东西（明确锚定）

- `resolve_config_for_part` 5 路径主流程
- `_validate_cached_decision` 三项校验
- `decisions_envelope` schema v2 + history log
- `toolbox_index.json` schema v1 + fingerprint
- in-process `_CONFIG_LIST_CACHE`（保留为 L2 cache）
- broker `msvcrt.locking` 文件锁（用于 decisions.json，不用于新 cache）

---

## §4 Data flow（4 个核心场景）

### 场景 A — 第一次 codegen（cache 全 miss）

| 步骤 | 动作 | spawn 次数 |
|---|---|---|
| 1 | resolver.prewarm(bom) → adapter.prewarm 收集 sldprt | 0 |
| 2 | broker.prewarm_config_lists(54 件) → cache=空 → miss=54 | 0 |
| 3 | spawn worker --batch (stdin: 54 sldprt) → 启 SW 一次 → loop 列 → stdout JSON | **1** |
| 4 | 写回 cache → atomic os.replace | 0 |
| 5 | BOM loop 内 broker.resolve_config_for_part → L2 miss → 持久化 cache 命中 → 填 L2 | 0 |
| **总计** | | **1** |

### 场景 B — 后续 codegen（同项目 + 没改）

| 步骤 | 动作 | spawn 次数 |
|---|---|---|
| 1 | resolver.prewarm(bom) → adapter.prewarm 收集 sldprt | 0 |
| 2 | broker.prewarm → cache 全命中 → miss=[] → 不 spawn | 0 |
| 3 | BOM loop 内 _list_configs_via_com 全走持久化 cache 命中 | 0 |
| **总计** | | **0** |

### 场景 C — 增量失效（用户改 1 件 sldprt）

| 步骤 | 失效检测 | spawn 次数 |
|---|---|---|
| 1 | broker.prewarm → cache 加载 OK | 0 |
| 2 | per-sldprt diff：53 件 mtime+size 同 → 命中；1 件 mtime 变 → miss | 0 |
| 3 | spawn worker --batch (stdin: 1 sldprt) → 列 1 件 → 写回 | **1** |
| 4 | BOM loop 全走持久化 cache 命中 | 0 |
| **总计** | | **1** |

### 场景 D — Envelope 失效（SW 升级 / Toolbox 路径变）

| 步骤 | 失效检测 | spawn 次数 |
|---|---|---|
| 1 | broker.prewarm → cache 加载 OK | 0 |
| 2 | envelope-level: cache.sw_version=23, current_sw_version=24 → 整 entries 清空 | 0 |
| 3 | miss = collect (BOM 全部 54 件) → batch spawn 一次 | **1** |
| **总计** | | **1**（一次性，~30-60s） |

### 4.1 Cache envelope schema (spec_v1)

```json
{
  "schema_version": 1,
  "generated_at": "2026-04-26T12:34:56+00:00",
  "sw_version": 24,
  "toolbox_path": "C:\\SOLIDWORKS Data\\Toolbox",
  "entries": {
    "C:\\SOLIDWORKS Data\\Toolbox\\GB\\bolts\\hex bolt.sldprt": {
      "mtime": 1714123456,
      "size": 245678,
      "configs": ["M3x10", "M3x12", "M4x16"]
    }
  }
}
```

**`_empty_config_lists_cache()` 返回形状**（5 字段全员就位，避免 KeyError 和 schema 漂移）：

```python
{
    "schema_version": CONFIG_LISTS_SCHEMA_VERSION,    # = 1
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "sw_version": None,                               # 故意 None → 触发 envelope_invalidated 走全 batch 重列
    "toolbox_path": None,                             # 同上
    "entries": {},
}
```

**`_envelope_invalidated(cache)` 判定**：
- `cache.get('sw_version') != detect_solidworks().version_year` → True
- `cache.get('toolbox_path') != detect_solidworks().toolbox_dir` → True
- 二者皆否 → False（envelope 仍有效，逐 entry 看 mtime/size）

### 4.2 Worker batch IPC 协议

**输入**：`subprocess.run([sys.executable, "tools/sw_list_configs_worker.py", "--batch"], input=json.dumps(["C:/path1.sldprt", "C:/path2.sldprt"]).encode(), timeout=180)`

**输出**（stdout JSON）：
```json
[
  {"path": "C:/path1.sldprt", "configs": ["A", "B"]},
  {"path": "C:/path2.sldprt", "configs": []}
]
```

**单件兼容模式（保留）**：现有 `subprocess.run([worker, sldprt_path])` 路径不动，broker fallback 路径仍能用。

---

## §5 Failure handling

### 5.1 Worker 启动失败 / SW 弹 modal / SW crash

```python
def prewarm_config_lists(sldprt_list: list[str]) -> None:
    """fire-and-forget；失败不抛（codegen 走单件 fallback 兜底）。"""
    if os.getenv("CAD_SW_BROKER_DISABLE") == "1":
        return                                                    # issue 9 安全阀
    cache = _load_config_lists_cache()
    if _envelope_invalidated(cache):
        cache = _empty_config_lists_cache()                       # SW 版本/Toolbox 路径变 → 整 entries 清
    miss = [p for p in sldprt_list if not _config_list_entry_valid(cache, p)]
    if not miss:
        return
    try:
        result = subprocess.run([worker, "--batch"],
                                input=json.dumps(miss).encode(),
                                capture_output=True, timeout=180)
        if result.returncode != 0:
            log.warning("config_lists batch worker rc=%d: %s",
                        result.returncode, result.stderr.decode()[:500])
            return  # cache 不动；BOM loop 走单件 fallback 兜底
        entries = json.loads(result.stdout)
        for entry in entries:
            cache['entries'][entry['path']] = {
                'mtime': _stat_mtime(entry['path']),
                'size': _stat_size(entry['path']),
                'configs': entry['configs'],
            }
        _save_config_lists_cache(cache)
    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError) as e:
        log.warning("config_lists prewarm 失败 %s; codegen 退化到单件 fallback", e)
        # 不抛异常 — prewarm 是加速优化不是必要前置
```

**核心原则**：prewarm 失败 = 退化到原行为，不是 codegen 失败。

### 5.2 Cache 文件损坏

```python
def _load_config_lists_cache() -> dict:
    if not path.exists():
        return _empty_config_lists_cache()
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError) as e:
        log.warning("config_lists cache 损坏，重建: %s", e)
        return _empty_config_lists_cache()
```

复用 `toolbox_index.json` 同模式（catalog.py:564）。损坏后下次 prewarm 走全 batch 重列 → 自愈。

### 5.3 schema 版本不符

```python
if cache.get('schema_version') != CONFIG_LISTS_SCHEMA_VERSION:
    log.info("config_lists schema bump %s → %s，重建",
             cache.get('schema_version'), CONFIG_LISTS_SCHEMA_VERSION)
    return _empty_config_lists_cache()
```

未来 v1→v2 升级（如改 entries 结构）走同样模式。**降级**（v2 cache 被 v1 broker 读）：版本不符视为空 → 不读错。

### 5.4 并发 codegen 抢同一 cache

两个进程并发跑（`gen_std_parts` + `sw-warmup --bom`）：

| 步骤 | 进程 A | 进程 B |
|---|---|---|
| 1 | _load → cache=空 |  |
| 2 | spawn worker batch | _load → cache=空 |
| 3 | worker 跑 30s | spawn worker batch |
| 4 | _save (.tmp + os.replace) | worker 跑 30s |
| 5 |  | _save (覆盖 A 的) |

**结果**：浪费一次 SW spawn，但不出错。最终 cache = B 写的。两进程都 PASS。

**为何不加文件锁**：
- config_lists 是"无副作用的查询结果"（重复 list 同一 sldprt 必返同结果）
- 锁会让进程 B 必等 A 30s — 反而劣化体验
- atomic write 保证文件不出现 partial state
- 简单 > 完美

### 5.5 NTFS mtime 漏抓

C 选项已用 `(mtime, size)` 二元组；NTFS 2s 精度漏抓 mtime 的同一秒内修改，size 兜底捕获（修改通常会改大小）。完全相同 size 的"重命名加内容微调" → 漏抓罕见。

如果未来发现真有 false-cache-hit，envelope 加 SHA1（schema_v2）—— 现在不做（YAGNI）。

---

## §6 Testing strategy

### 6.1 测试矩阵

| 类别 | 测试文件 | 覆盖点 |
|---|---|---|
| **A. envelope 单元** | `tests/test_sw_config_lists_cache.py` 新建 | _load/_save schema v1 round-trip / 损坏文件 → empty / schema 版本不符 → empty / 空 cache 写入 |
| **B. 失效逻辑单元** | 同上 | mtime 变 / size 变 / sw_version 变 → entries 全清 / toolbox_path 变 → entries 全清 / 全无变化 → cache_hit |
| **C. broker.prewarm 集成** | `tests/test_sw_config_broker.py` 末尾 | 全 cache miss → 1 次 batch spawn 写回 / 全命中 → 0 spawn / 部分 miss → batch worker 收 miss list / worker 失败 → cache 不动 prewarm 不抛 |
| **D. worker batch IPC** | `tests/test_sw_list_configs_worker_batch.py` 新建 | --batch + stdin JSON list → stdout JSON list / 单件 CLI 模式仍 work / SW 启动失败 → exit code + stderr |
| **E. 端到端调用链** | `tests/test_sw_toolbox_adapter_with_broker.py` 末尾 | gen_std_parts BOM → resolver.prewarm 派发 → adapter.prewarm 收集 sldprt → broker.prewarm 1 次 batch → loop 内 0 fallback spawn |

### 6.2 测试 mock 复用

- 现有 `patch_broker_to_return` helper 不动
- 新加 `patch_broker_prewarm_returns(monkeypatch, lookup)` 让 e2e 测试 mock prewarm 行为
- conftest autouse `disable_sw_config_broker_by_default` 不动；prewarm 同样默认禁用
- 新 fixture `tmp_config_lists_cache(monkeypatch, tmp_path)` 隔离 cache 文件路径

### 6.3 TDD 顺序

1. envelope schema → 持久化读写（A+B，无 SW 依赖，最快）
2. broker.prewarm_config_lists API（C，mock worker subprocess）
3. worker --batch 模式（D，纯 CLI/IPC 测，无 SW）
4. adapter.prewarm 实现（E 单层）
5. resolver.prewarm 派发（E 单层）
6. gen_std_parts 入口加 prewarm（E 全链）

### 6.4 Coverage 校准点

跑独立脚本（仿 `tools/render_regression.py` 模式）：
- 跑两次 `cad-codegen tests/fixtures/end_effector_spec.md` 测 timing
- 期望：第二次 < 第一次 50%
- 期望：spawn worker 计数 = 1（第一次） / 0（第二次）

---

## §7 Backwards compatibility

### 7.1 新文件 → 老 broker 读取

不存在该问题：新文件不存在时 `_empty_config_lists_cache()` 视为空 → 走原行为（fallback 单件 spawn）。

### 7.2 Schema v1 → v2 演化

未来需要更严格失效信号（如加 SHA1）时：
- `SCHEMA_VERSION = 2`
- `_load_config_lists_cache` 检测旧 v1 → 视为空 → 自愈重建

### 7.3 PartsAdapter base class 加 prewarm 接口

- 基类 `prewarm(bom_queries) -> None` 是 **virtual method with default no-op body**（不是 abstractmethod）→ 现有 adapter（jinja_primitive / step_pool / partcad / bd_warehouse）无需改动
- sw_toolbox_adapter override 实现实际收集 + broker.prewarm_config_lists 调用
- 选 virtual + default no-op（vs abstractmethod + 4 个 adapter 各加 `pass`）：避免对未来新 adapter 的强制实施摩擦

### 7.4 Worker --batch flag

- 单件 CLI 模式（`worker.py path.sldprt`）保留
- 新 `--batch` flag opt-in；现有 broker fallback 路径继续用单件模式

---

## §8 Out of scope（明确不做）

- **content SHA1 失效**（D 选项）—— 性能开销不必要，YAGNI
- **long-running worker / IPC 长连接**（Approach C）—— 进程生命周期管理复杂度高
- **跨用户共享 cache** —— ~/.cad-spec-gen 已是 per-user，跨用户违反 isolation
- **cache 大小限制 / LRU 驱逐** —— GB 1818 件 × 每件 ~200 字节 entry = ~400 KB JSON，无 LRU 必要
- **partcad / bd_warehouse 的 prewarm 实现** —— 仅为 sw_toolbox 实现；其他 adapter 走 base default no-op；未来如发现也慢再加
- **Task 16 / Task 17 / Task 18+ 的 broker pending 流程** —— 与本 spec 正交（CP-6 流程）

---

## §9 Open questions（plan 阶段需澄清）

无 —— brainstorming 已答清 Q1-Q3 + approach 选择；剩余实施细节属于 plan 范畴。

---

## §10 References

- `adapters/solidworks/sw_config_broker.py:440-500` — 现 `_CONFIG_LIST_CACHE` + `_list_configs_via_com` 实现
- `adapters/solidworks/sw_toolbox_catalog.py:541-598` — `load_toolbox_index` 失效模式可参考
- `tools/sw_list_configs_worker.py` — 现有 worker 单件模式（待加 --batch）
- `adapters/parts/sw_toolbox_adapter.py:303-372` — 现有 `find_sldprt` API（catalog-only，prewarm 复用）
- `codegen/gen_std_parts.py:270-312` — 现有 generation loop（prewarm 加在前）
- spec rev 2: `docs/superpowers/specs/2026-04-25-sw-toolbox-llm-config-broker-design.md`
- 用户北极星 memory：`project_north_star.md`
