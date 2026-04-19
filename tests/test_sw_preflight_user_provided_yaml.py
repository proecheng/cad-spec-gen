"""Task 24 — append_yaml_mapping 追加规则 + provenance 字段 + 损坏 3 类兜底测试"""
import shutil
from pathlib import Path
import yaml


def test_append_mapping_to_empty_yaml(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from sw_preflight.user_provided import append_yaml_mapping
    src = tmp_path / 'm3x8.step'
    src.write_bytes(b'ISO-10303\n' + b'\n' * 20000)
    dest = tmp_path / 'std_parts/user_provided/standard/m3x8.step'
    dest.parent.mkdir(parents=True)
    # 偏离 plan：plan 原文是 src.rename(dest) 但会导致 source_path.stat() 打不到源文件；
    # 按 provenance 设计意图应为复制（源文件保留以供后续校验），改 shutil.copy2
    shutil.copy2(src, dest)
    append_yaml_mapping({'name_cn': 'GB/T 70.1 M3×8'}, dest, source_path=src)
    cfg = yaml.safe_load(Path('parts_library.yaml').read_text(encoding='utf-8'))
    mapping = cfg['mappings'][0]
    assert mapping['adapter'] == 'step_pool'
    assert 'GB/T 70.1 M3×8' in mapping['match']['keyword_contains']
    assert 'provenance' in mapping
    assert mapping['provenance']['provided_by_user'] is True
    assert 'source_hash' in mapping['provenance']
    assert mapping['provenance']['source_hash'].startswith('sha256:')


def test_append_inserts_before_any_true(tmp_path, monkeypatch):
    """新规则应插在第一个 {any: true} 规则之前"""
    monkeypatch.chdir(tmp_path)
    Path('parts_library.yaml').write_text(yaml.dump({
        'mappings': [
            {'match': {'category': 'fastener'}, 'adapter': 'sw_toolbox'},
            {'match': {'any': True}, 'adapter': 'jinja_primitive'},
        ]
    }), encoding='utf-8')
    from sw_preflight.user_provided import append_yaml_mapping
    src = tmp_path / 'm3x8.step'
    src.write_bytes(b'ISO-10303\n' + b'\n' * 20000)
    append_yaml_mapping({'name_cn': 'TEST'}, Path('std_parts/test.step'), source_path=src)
    cfg = yaml.safe_load(Path('parts_library.yaml').read_text(encoding='utf-8'))
    # 新规则应该在 index 1（fastener 之后、{any:true} 之前）
    assert cfg['mappings'][1]['match']['keyword_contains'] == ['TEST']
    assert cfg['mappings'][2]['match'] == {'any': True}


def test_append_yaml_syntax_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path('parts_library.yaml').write_text("mappings:\n  - match: {any: true\n  adapter: jp",
                                          encoding='utf-8')
    from sw_preflight.user_provided import append_yaml_mapping
    import pytest
    with pytest.raises(ValueError, match='YAML 语法错误'):
        src = tmp_path / 'src.step'
        src.write_bytes(b'ISO-10303\n')
        append_yaml_mapping({'name_cn': 'TEST'}, Path('dest.step'), source_path=src)


def test_append_yaml_schema_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path('parts_library.yaml').write_text("mappings:\n  some_key: some_value", encoding='utf-8')
    from sw_preflight.user_provided import append_yaml_mapping
    import pytest
    with pytest.raises(ValueError, match='mappings 应为列表'):
        src = tmp_path / 'src.step'
        src.write_bytes(b'ISO-10303\n')
        append_yaml_mapping({'name_cn': 'TEST'}, Path('dest.step'), source_path=src)
