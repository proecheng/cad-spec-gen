"""tests/test_sw_preflight_cache.py — sw_preflight.cache IPC + TTL 测试（Task 19）。

覆盖 plan 1768-1794 行 3 场景：
  1. write → read 在 TTL 内命中
  2. 过期后 read 返回 None
  3. schema_version 不匹配时 read 返回 None
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_write_then_read_within_ttl(tmp_path):
    """写入后立即读取应返回完整 payload（含 schema_version 元数据）。"""
    from sw_preflight import cache

    path = tmp_path / "cache.json"
    cache.write_cache(path, {"sw_year": 2024, "ok": True}, ttl_sec=300, ran_by_entry="cli")

    data = cache.read_cache(path)
    assert data is not None
    assert data["sw_year"] == 2024
    assert data["ok"] is True
    assert data["schema_version"] == cache.SCHEMA_VERSION
    assert data["ran_by_entry"] == "cli"


def test_expired_cache_returns_none(tmp_path):
    """ran_at 早于 ttl_seconds 前应视为过期，read_cache 返回 None。"""
    from sw_preflight import cache

    path = tmp_path / "cache.json"
    # 手工构造一个 10 分钟前写入、TTL 仅 60 秒的缓存
    stale_time = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    payload = {
        "schema_version": cache.SCHEMA_VERSION,
        "ran_at": stale_time,
        "ran_by_entry": "cli",
        "ttl_seconds": 60,
        "sw_year": 2024,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert cache.read_cache(path) is None


def test_schema_mismatch_returns_none(tmp_path):
    """schema_version 与当前常量不一致时应视为不可用，read_cache 返回 None。"""
    from sw_preflight import cache

    path = tmp_path / "cache.json"
    payload = {
        "schema_version": cache.SCHEMA_VERSION + 99,  # 未来版本
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "ran_by_entry": "cli",
        "ttl_seconds": 300,
        "sw_year": 2024,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert cache.read_cache(path) is None
