# SwComSession 线程模型（Part 2a）

## 背景

COM 接口非线程安全（v4 决策 #22）。Part 1 用 `self._lock` 全方法包裹 `convert_sldprt_to_step`，避免两个线程同时调 COM。Part 2 要加入 `start()` / `_maybe_restart()` / idle shutdown，锁粒度若处理不当会死锁。

关键常量（定义在 `adapters/solidworks/sw_com_session.py` 顶部）：`RESTART_EVERY_N_CONVERTS = 50`（决策 #11），`IDLE_SHUTDOWN_SEC = 300`（5 分钟），`COLD_START_TIMEOUT_SEC = 90`，`SINGLE_CONVERT_TIMEOUT_SEC = 20`（决策 #36，2026-04-16 由 30 下调），`CIRCUIT_BREAKER_THRESHOLD = 3`。

## 状态转换

```
  ┌───────────────┐  start() 成功 ┌─────────────┐
  │ UNINITIALIZED ├──────────────▶│   RUNNING   │
  │  (_app=None)  │               │ (_app≠None) │
  └──────┬────────┘               └──────┬──────┘
         │                               │
         │ start() 失败                  │ convert 50 次
         │ / cold timeout                │
         ▼                               ▼
  ┌───────────────┐                ┌─────────────┐
  │   UNHEALTHY   │◀───熔断────────│  RESTARTING │
  │(_unhealthy=T) │  (连续3次失败) │ shutdown + start│
  └───────────────┘                └─────────────┘
                                          │
                                          │ idle 5min
                                          ▼
                                   ┌─────────────┐
                                   │  SHUTDOWN   │
                                   │ _app=None   │
                                   └─────────────┘
```

## 锁粒度规则

1. **`_lock` 是 `threading.Lock()`（非重入，非 `RLock`），保护 session 内的所有状态**。`_SINGLETON_LOCK` 是模块级锁，只保护 singleton 实例化。选 `Lock` 而非 `RLock` 是刻意的——强制所有持锁方法走 `_*_locked` 命名约定的单一入口，杜绝同一线程内嵌套 acquire 的隐患。
2. **持 `_lock` 的操作 → 可以调 COM**。不持锁调 COM = race。
3. **`_unhealthy=True` 后 session 进入死态**——所有 `convert_sldprt_to_step` 调用立即返回 False，`_maybe_restart_locked` 也不再尝试重启。恢复路径只有 `reset_session()`：该方法会先 `shutdown()` 再清空 singleton，下次 `get_session()` 会返回一个崭新的 `SwComSession`（`_unhealthy=False`）。
4. **持 `_lock` 时禁止 acquire `_SINGLETON_LOCK`**（避免嵌套死锁；singleton 在 convert 内部不会被重建）。
5. **所有可能触发 `start()` 的入口必须已经持 `_lock`**：convert 内若发现 `_app is None` 走 `_start_locked()`，不重新 acquire。
6. **idle shutdown 不能阻塞 convert**：采用 opportunistic 模型——每次 convert 入口检查 `time.time() - _last_used_ts >= IDLE_SHUTDOWN_SEC`，命中则先 shutdown 再 start，全程在同一 `_lock` 里。不引入后台线程。
   
   `_last_used_ts` 的语义是"**上次成功 convert 的时间戳**"（在 `convert_sldprt_to_step` 成功分支里更新）。选择"成功时更新"而非"入口时更新"，是因为我们要测量的是"距上次产出 STEP 多久"——失败的 convert 不算产出活动，不应推迟 idle 释放。`_last_used_ts == 0.0` 时（session 还没成功转换过任何一个零件）跳过 idle 判定。
7. **restart 同样 in-band**：`convert` 成功后计数，达到 `RESTART_EVERY_N_CONVERTS` 时在下一次 convert 入口先触发 restart。

## 为什么不引入后台线程做 idle shutdown？

- 后台线程做 shutdown 要 acquire `_lock`，但 `_lock` 在 convert 期间被长期持有（单转最长 30s）。后台线程会长时间 block。
- 即使后台线程能抢到锁，shutdown 后 convert 若恢复需要重新 start，增加状态机复杂度。
- Opportunistic 模型天然避免并发：下次 convert 发现空闲 → shutdown → restart，状态转换线性化。
- 成本：若 session 空闲超过 `IDLE_SHUTDOWN_SEC` 但永远无下一次 convert，SW 进程不释放。这由 `reset_session()`（`reset_all_sw_caches` 调用链）兜底，可接受。

## `_lock` vs `threading.Timer`

本模型**不使用** Timer 或后台线程。理由同上。`SINGLE_CONVERT_TIMEOUT_SEC` 的超时保护已在 Part 2c P0 落地——**subprocess-per-convert 隔离**（每次 convert 独立进程，subprocess.run 守 timeout）+ 20s timeout 值（决策 #36，基于 Part 2c P0 真 SW smoke 5 件均值 11.6s × 1.72x 冗余）。

## 契约

- **`start()` 必须在 `_lock` 内调用** — 约定：只在 `_start_locked()` 方法存在，外部不直接调
- **`convert_sldprt_to_step` 是唯一可能触发状态转换的入口** — 所有生命周期副作用在此方法串行化
- **`shutdown()` 可在 `_lock` 外调用**（用于 `reset_session()` 测试兜底）——shutdown 自行 acquire `_lock`
- **`reset_session()` 会调 `shutdown()`** — 外部测试通过此入口清除状态
