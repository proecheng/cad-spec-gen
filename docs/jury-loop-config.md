# enhance.jury_loop — AI 自动重试闭环配置说明

> **一句话**：开了这个开关，`cad-spec-gen enhance` 会让 AI 给每张增强图打分；分数不够的，自动按问题反馈重写一次，选更好的那张交付。默认开启，不会重复花钱。

## 1. 这是什么

普通流程：渲染图 → AI 增强 → 交付。
开了闭环：渲染图 → AI 增强（首轮）→ **AI 评分** → 分数 < 阈值就 **按问题反馈自动重试一次** → 评分对比 → **选高分那张交付**。

- 评分用的是你在 `~/.claude/cad_jury_config.json` 里配的同一个 AI 服务（见 [cad-jury-config.md](cad-jury-config.md)）。**没配 jury → 闭环自动跳过，什么都不会多发生。**
- 重试用的是另一个图生图后端（默认 Google Gemini chat-image）。
- 选张策略默认 `pick_max_jury`：重试平分/降分时退回首轮图——**闭环永远不会让交付质量变差**。

## 2. 怎么开关

闭环**默认开启**（零配置）。要关掉或调整，在项目根目录 `pipeline_config.json` 的 `enhance` 段下加 `jury_loop` 子段：

```jsonc
{
  "enhance": {
    "model": "...",
    "jury_loop": {
      "enabled": true,            // 总开关。false = 跑一次就交付，不进闭环
      "cost_cap_usd": 1.5,        // 全口径预算上限（约 ¥10 / 跑全 5 视角）；超额自动停
      "backend": {
        "kind": "gemini_chat_image",   // 重试后端类型（gemini_chat_image / openai_images_edit / comfyui_workflow_cloud）
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "api_key_env": "GEMINI_API_KEY",
        "model_name": "gemini-2.5-flash-image",
        "timeout_s": 180
      },
      "advanced": {               // 高级项，默认请勿动
        "threshold": 75,          // photoreal_score < threshold 才触发重试（65 低槛 / 75 默认 / 85 严苛）
        "max_retries": 1,         // SP1 单轮重试
        "llm_fallback": false,    // 评分反馈识别不出已知问题时，是否用 AI 兜底翻译
        "rule_table_path": null,  // 自定义重试规则 yaml 路径（null = 用内置规则；必须在项目目录内）
        "score_select_strategy": "pick_max_jury"  // pick_max_jux | force_retry
      }
    }
  }
}
```

> `pipeline_config.json` 是 per-machine 配置（git 里标了 skip-worktree，每台机器自己的值不会进版本库）。不写 `jury_loop` 段时用代码内嵌的默认（即上面的值）。

**回退到旧版本**：把 `enabled` 改成 `false` 即可——闭环不跑，交付报告也不会多出 `loop_summary` 段，旧版解析器读着不会报错。

## 3. cost 估算

| 场景 | 额外花费（估算，参考用） |
|---|---|
| 全 5 视角，3 张首轮达标 / 2 张触发重试 | ≈ $0.36 ≈ ¥2.6 |
| 全 5 视角全部触发重试（最坏） | ≈ $0.90 ≈ ¥6.5 |
| `cost_cap_usd` 默认 1.5 USD | 约 5 视角×0.25 + 安全余量；超额自动停 |

实际以服务商账单为准；汇率按 ¥7.2/$ 近似换算。每张额外花费 = 一次重试图生图 + 一次重新评分（pick_max_jury 模式）。

## 4. 跑完看哪里

- `<render_dir>/<视角>_enhance_meta.json` —— 每个视角一份「明细单」：首轮分数 / 重试分数 / 命中的问题标签 / 用了哪些重写规则 / 这张额外花了多少。
- `<render_dir>/ENHANCEMENT_REPORT.json` 顶层多了 `loop_summary` 段（`enabled=false` 时没有），第一屏就是三个数字 + 中文摘要：
  ```json
  "loop_summary": {
    "headline": {"improved_views": 2, "score_gain_total": 35, "extra_cost_cny": 2.6},
    "user_friendly_summary": "5 视角中：3 张接受首轮 / 2 张闭环成功（合计提升 35 分）。本次额外花费约 ¥2.6。",
    ...
  }
  ```
- 终端日志末尾会打一行 `Loop summary: ...` 概要。

## 5. 幂等与重跑

- **默认幂等**：重复跑 `cad-spec-gen enhance` 不会重复花钱——已经成功交付（或确认是持久性失败如 API key 无效 / 余额不足）的视角会 fast-path 跳过。
- **改了规则想重刷**：`cad-spec-gen enhance --rerun-loop` 强制所有视角重新跑首轮 + 闭环，覆盖旧明细单。
- **临时性失败**（评分服务挂了 / 限流 / 重试调用失败）默认下次跑会**自动重试**——相当于"上次没成这次再试"。

## 6. 常见问题

| 现象 | 原因 / 处理 |
|---|---|
| 跑完没有 `loop_summary` 段 | `enable=false`，或这次跑没经过闭环 hook（baseline 增强没产出图） |
| 日志说"jury 未配置或配置错误，本次跑跳过闭环" | 没配 `~/.claude/cad_jury_config.json`，或配错了——闭环整体禁用，首轮图直接交付。配好后再跑 |
| `loop_status=retry_auth_failed` | 重试后端的 API key（默认 `GEMINI_API_KEY`）无效——检查环境变量。修好后用 `--rerun-loop` 重试 |
| `loop_status=retry_quota_exceeded` | 重试后端账户余额不足——充值后用 `--rerun-loop` 重试 |
| `loop_status=cost_capped` | 本次预算 `cost_cap_usd` 耗尽，剩余视角接受首轮图。调大 `cost_cap_usd` 或下次再跑（新预算）|
| `loop_status=above_threshold` | 首轮分数已达标，没必要重试——这是好事 |
| `loop_status=jury_unavailable` | 评分服务这次没返回结果，接受首轮图。下次跑会自动重试 |
| 想用自己的重试规则 | 写一个 rule yaml（schema_version=1），路径填到 `advanced.rule_table_path`（必须在项目目录内）|

## 7. 关联文档

- [cad-jury-config.md](cad-jury-config.md) —— 评分 AI 服务配置（`~/.claude/cad_jury_config.json`）；闭环复用它的服务
- 设计细节见 `docs/superpowers/specs/2026-05-10-jury-prompt-loop-design.md`（开发者向）
