from pathlib import Path
import pytest


def test_cache_schema_version_is_2():
    from sw_preflight.cache import SCHEMA_VERSION
    assert SCHEMA_VERSION == 2


def test_v1_cache_read_returns_none(tmp_path):
    """旧 schema_version=1 的 cache → read_cache 返回 None（视为 miss）。"""
    import json
    from datetime import datetime, timezone
    from sw_preflight.cache import read_cache

    cache_file = tmp_path / "preflight_cache.json"
    cache_file.write_text(json.dumps({
        "schema_version": 1,
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "ttl_seconds": 300,
        "passed": True,
    }), encoding="utf-8")

    result = read_cache(cache_file)
    assert result is None  # schema 不匹配 → miss


def test_v2_cache_read_succeeds(tmp_path):
    """schema_version=2 在 TTL 内 → read_cache 正常返回。"""
    import json
    from datetime import datetime, timezone
    from sw_preflight.cache import read_cache, SCHEMA_VERSION

    cache_file = tmp_path / "preflight_cache.json"
    cache_file.write_text(json.dumps({
        "schema_version": SCHEMA_VERSION,
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "ttl_seconds": 300,
        "passed": True,
    }), encoding="utf-8")

    result = read_cache(cache_file)
    assert result is not None
    assert result["passed"] is True
