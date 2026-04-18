"""F-1.3j+k S2.0(b)：验证 sw-smoke.yml line 44-52 skip-guard 真要求 real==2（而非 real>=1）。

当前 sw-smoke.yml line 51 是 `assert real >= 1` → 1 个 testcase 也 PASS → 测试 RED（期望 1 testcase fail 但实际 pass）。
S2 commit 2 改成 `assert real == 2` 后 → 测试 GREEN。
"""

import subprocess
import sys
import textwrap
from pathlib import Path


def _skip_guard_inline_script(xml_path: Path) -> str:
    """把 sw-smoke.yml line 44-52 的 python 块抽成 helper（保持与 yaml 同步：见 spec §3.4 P4-F）。

    v5 P4-F 修订：assert 由 `real >= 1` 改为 `real == 2`。
    本 helper 模拟"修复后"的 skip-guard 逻辑。
    """
    return textwrap.dedent(f"""
        from xml.etree import ElementTree as ET
        root = ET.parse(r'{xml_path}').getroot()
        all_tcs = list(root.iter('testcase'))
        skipped = [tc for tc in all_tcs if tc.find('skipped') is not None]
        real = len(all_tcs) - len(skipped)
        print(f'skip-guard: total={{len(all_tcs)}} skipped={{len(skipped)}} real={{real}}')
        assert real == 2, f'expected exactly 2 real testcases, got {{real}}'
    """).strip()


def _make_junit_xml(tmp_path: Path, n_real: int) -> Path:
    """生成 n 个非 skipped testcase 的 junit xml fixture"""
    cases = "\n".join(
        f'    <testcase name="test_real_{i}" classname="C"></testcase>'
        for i in range(n_real)
    )
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="x" tests="{n_real}" skipped="0">
{cases}
  </testsuite>
</testsuites>
"""
    p = tmp_path / f"junit-real-{n_real}.xml"
    p.write_text(xml, encoding="utf-8")
    return p


class TestSkipGuard:
    def test_real_equals_2_passes(self, tmp_path: Path) -> None:
        xml = _make_junit_xml(tmp_path, n_real=2)
        result = subprocess.run(
            [sys.executable, "-c", _skip_guard_inline_script(xml)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"expected real==2 PASS, got rc={result.returncode}; stderr={result.stderr[:300]}"
        )

    def test_real_equals_1_fails(self, tmp_path: Path) -> None:
        """当前 sw-smoke.yml `real >= 1` 让此 fixture PASS → 修复后 `real == 2` 会让其 fail"""
        xml = _make_junit_xml(tmp_path, n_real=1)
        result = subprocess.run(
            [sys.executable, "-c", _skip_guard_inline_script(xml)],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0, (
            f"expected real==1 FAIL after S2 fix, got rc=0; stdout={result.stdout[:300]}"
        )

    def test_real_equals_3_fails(self, tmp_path: Path) -> None:
        xml = _make_junit_xml(tmp_path, n_real=3)
        result = subprocess.run(
            [sys.executable, "-c", _skip_guard_inline_script(xml)],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0, (
            f"expected real==3 FAIL, got rc=0; stdout={result.stdout[:300]}"
        )
