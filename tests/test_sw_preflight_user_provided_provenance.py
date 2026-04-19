"""Task 25 — check_provenance_validity 三态返回测试（valid / changed / source_missing）"""
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import patch


def test_provenance_check_source_unchanged(tmp_path):
    src = tmp_path / 'src.step'
    src.write_bytes(b'ISO-10303\n' + b'\n' * 20000)
    from sw_preflight.user_provided import check_provenance_validity, _file_sha256
    mapping = {'provenance': {
        'source_path': str(src),
        'source_hash': _file_sha256(src),
        'source_mtime': datetime.fromtimestamp(src.stat().st_mtime, timezone.utc).isoformat(),
    }}
    result = check_provenance_validity(mapping)
    assert result == 'valid'


def test_provenance_check_source_changed(tmp_path):
    src = tmp_path / 'src.step'
    src.write_bytes(b'ISO-10303\n' + b'\n' * 20000)
    from sw_preflight.user_provided import check_provenance_validity
    mapping = {'provenance': {
        'source_path': str(src),
        'source_hash': 'sha256:WRONGHASH',  # 故意错
        'source_mtime': datetime.now(timezone.utc).isoformat(),
    }}
    result = check_provenance_validity(mapping)
    assert result == 'changed'


def test_provenance_check_source_missing(tmp_path):
    from sw_preflight.user_provided import check_provenance_validity
    mapping = {'provenance': {
        'source_path': str(tmp_path / 'doesnotexist.step'),
        'source_hash': 'sha256:WHATEVER',
        'source_mtime': datetime.now(timezone.utc).isoformat(),
    }}
    result = check_provenance_validity(mapping)
    assert result == 'source_missing'
