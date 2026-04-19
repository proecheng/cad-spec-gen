"""sw_preflight/io.py — STEP 三层校验测试（Task 11）。

三层校验顺序：扩展名 → 大小 → 魔数头（cadquery 解析在 Task 24 再补）。
覆盖：
- 扩展名非 .step/.stp → invalid_ext
- 大小 < 10KB → too_small
- 大小 > 500MB → too_large
- 前 50 字节无 ISO-10303 → invalid_magic
- 合法 STEP → valid
"""
from pathlib import Path


def test_ext_check_rejects_stl(tmp_path):
    f = tmp_path / 'file.stl'
    f.write_text('foo')
    from sw_preflight.io import validate_step_file
    result = validate_step_file(f)
    assert result.kind == 'invalid_ext'


def test_size_too_small(tmp_path):
    f = tmp_path / 'tiny.step'
    f.write_text('x')  # 1 byte < 10KB
    from sw_preflight.io import validate_step_file
    result = validate_step_file(f)
    assert result.kind == 'too_small'


def test_size_too_large(tmp_path):
    f = tmp_path / 'huge.step'
    f.write_bytes(b'x' * (501 * 1024 * 1024))  # 501MB > 500MB
    from sw_preflight.io import validate_step_file
    result = validate_step_file(f)
    assert result.kind == 'too_large'


def test_magic_header_invalid(tmp_path):
    f = tmp_path / 'fake.step'
    f.write_bytes(b'not iso 10303' + b'x' * 20000)
    from sw_preflight.io import validate_step_file
    result = validate_step_file(f)
    assert result.kind == 'invalid_magic'


def test_valid_step_file(tmp_path):
    f = tmp_path / 'valid.step'
    f.write_bytes(b'ISO-10303-21;\nHEADER;\n' + b'\n' * 20000)
    from sw_preflight.io import validate_step_file
    result = validate_step_file(f)
    assert result.kind == 'valid'
