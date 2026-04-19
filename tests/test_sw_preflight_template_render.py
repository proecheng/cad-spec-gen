# tests/test_sw_preflight_template_render.py
# Task 27 — 验证 sw_report.html.j2 模板渲染三段 + 状态卡 + 折叠区
from pathlib import Path


def test_template_renders_three_sections(tmp_path):
    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader('sw_preflight/templates'))
    tpl = env.get_template('sw_report.html.j2')
    html = tpl.render(
        sw_status={'edition': 'Pro 2024', 'toolbox': True, 'pywin32': True},
        ran_at='2026-04-19T14:32:00Z', elapsed='2m18s',
        standard_rows=[{'status': '✅', 'name': 'GB/T 70.1 M6', 'adapter': 'sw_toolbox'}],
        vendor_rows=[{'status': '✅', 'name': 'Maxon ECX', 'adapter': 'step_pool'}],
        custom_rows=[{'status': '✅', 'name': '立柱 P1-001', 'adapter': 'jinja_primitive'}],
        fix_records=[{'action': '程序残留清理', 'elapsed_ms': 1200,
                      'detail': 'ROT 释放 1 个僵死 SLDWORKS 实例'}],
    )
    assert 'SW 资产报告' in html
    assert '标准件' in html
    assert '外购件' in html
    assert '自定义件' in html
    assert '后台修复记录' in html
    assert '<details>' in html  # 折叠区给技术细节
    assert 'Pro 2024' in html
