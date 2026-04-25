"""adapters/solidworks/sw_config_broker.py — SW Toolbox 配置名匹配 broker。

设计参见 docs/superpowers/specs/2026-04-25-sw-toolbox-llm-config-broker-design.md (rev 2)。

主流程：
1. SW COM 列 SLDPRT 当前可用 configurations
2. 读 spec_decisions.json 缓存命中 + 三项校验 → 直接返回 cached_decision
3. 规则匹配 BOM dim → config (L1 精确 / L2 子串)，confidence ≥ 0.7 → auto
4. 含糊匹配 → 看 CAD_AMBIGUOUS_CONFIG_POLICY env：
   - "halt"（默认）→ 抛 NeedsUserDecision
   - "fallback_cadquery" → 返回 policy_fallback ConfigResolution（仍累积 pending）
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ConfigResolution:
    """broker 返回的解析结果。

    confidence 取值表（详见 spec §4.1）:
        source="cached_decision":  1.0 （用户已确认）
        source="auto" + L1 精确:    1.0 （字面完全匹配）
        source="auto" + L2 子串:    0.7 ~ 0.95 （依命中长度）
        source="policy_fallback":   0.0 （非匹配，env var 强制 fallback）
    """

    config_name: str | None
    source: str  # "cached_decision" | "auto" | "policy_fallback"
    confidence: float
    available_configs: list[str]
    notes: str = ""


class NeedsUserDecision(Exception):
    """broker 在含糊匹配 + policy="halt" 时抛此异常。

    sw_toolbox_adapter 捕获后 return miss；
    gen_std_parts 累积所有抛出的 record 后一次性原子写 pending 文件。
    broker 自身不写 pending（rev 2 修订）—— 异常携带 record，避免进程崩溃时部分写入。
    """

    def __init__(self, part_no: str, subsystem: str, pending_record: dict):
        self.part_no = part_no
        self.subsystem = subsystem
        self.pending_record = pending_record
        super().__init__(f"User decision needed for {subsystem}/{part_no}")
