"""SW 预检报告生成 — 三段式 HTML + JSON，术语去技术化。"""
import json
from pathlib import Path
from dataclasses import asdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional
from jinja2 import Environment, FileSystemLoader
from sw_preflight.types import PreflightResult, BomDryRunResult, FixRecord

if TYPE_CHECKING:
    from parts_resolver import ResolveReport


# 术语去技术化映射（用户界面不暴露 ROT / HKCU / CLSID 等技术名）
ACTION_FRIENDLY = {
    'rot_orphan_release': '程序残留清理',
    'pywin32_install': 'Python 通信组件安装',
    'addin_enable': 'Toolbox 模块自动启用',
    'sw_launch_background': 'SOLIDWORKS 后台启动',
}


def _friendly_action(action: str) -> str:
    """将 action 技术名映射为用户可读的中文术语。未命中映射则原样返回。"""
    return ACTION_FRIENDLY.get(action, action)


def _friendly_detail(record: FixRecord) -> str:
    """折叠区内的技术细节（非折叠区保持友好术语）"""
    if record.action == 'rot_orphan_release':
        return 'ROT 释放 1 个僵死 SLDWORKS 实例 (技术名: Running Object Table)'
    return f"{record.before_state} → {record.after_state}"


def emit_report(bom_rows: list[dict], dry_run: BomDryRunResult,
                preflight: PreflightResult, output_dir: Path,
                resolve_report: Optional["ResolveReport"] = None) -> Path:
    """生成 sw_report.html + sw_report_data.json，返回 HTML 路径"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 按 PartCategory 分三段
    standard_rows, vendor_rows, custom_rows = [], [], []
    for o in list(dry_run.hit_rows) + list(dry_run.stand_in_rows):
        entry = {
            'status': o.status,
            'name': o.bom_row.get('name_cn', '?'),
            'adapter': o.actual_adapter,
            'reason': o.diagnosis.reason if o.diagnosis else None,
            'suggestion': o.diagnosis.suggestion if o.diagnosis else None,
        }
        if o.category.value.startswith('standard'):
            standard_rows.append(entry)
        elif o.category.value == 'vendor_purchased':
            vendor_rows.append(entry)
        else:
            custom_rows.append(entry)

    # fix_records 用友好术语 + 折叠详情
    fix_records = [
        {'action': _friendly_action(f.action),
         'elapsed_ms': f.elapsed_ms,
         'detail': _friendly_detail(f)}
        for f in preflight.fixes_applied
    ]

    # sw_status 摘要
    edition_str = 'unknown'
    try:
        if preflight.sw_info is not None:
            edition_str = f"{preflight.sw_info.edition} {preflight.sw_info.version_year}"
    except Exception:
        pass

    toolbox_advisory = "addin_enabled" in getattr(preflight, "advisory_failures", {})
    sw_status = {
        'edition': edition_str,
        'toolbox': preflight.passed,
        'toolbox_advisory': toolbox_advisory,
        'pywin32': True,  # 能跑到这里说明 pywin32 已装（preflight 前置 check 过）
    }

    # 渲染 HTML
    env = Environment(loader=FileSystemLoader(str(Path(__file__).parent / 'templates')))
    tpl = env.get_template('sw_report.html.j2')
    html = tpl.render(
        sw_status=sw_status,
        ran_at=datetime.now(timezone.utc).isoformat(),
        elapsed='?',  # 从 preflight.per_step_ms 能算出来，但本 task 不做
        standard_rows=standard_rows,
        vendor_rows=vendor_rows,
        custom_rows=custom_rows,
        fix_records=fix_records,
        resolve_report=resolve_report.to_dict() if resolve_report is not None else None,
    )
    html_path = output_dir / 'sw_report.html'
    html_path.write_text(html, encoding='utf-8')

    # JSON 副本（机读用）
    json_path = output_dir / 'sw_report_data.json'
    json_path.write_text(json.dumps({
        'sw_status': sw_status,
        'standard_rows': standard_rows,
        'vendor_rows': vendor_rows,
        'custom_rows': custom_rows,
        'fix_records': [asdict(f) for f in preflight.fixes_applied],
    }, default=str, indent=2), encoding='utf-8')
    return html_path
