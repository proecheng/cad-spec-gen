"""解析 pytest --junitxml 产物为 {passed, failed, failed_tests}。

用于 SW-B9 Stage D 装配回归 before/after 对比。
使用 stdlib xml.etree.ElementTree 避免引入 pytest-json-report 依赖。
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


def parse_junit_xml(xml_path: Path) -> dict[str, Any]:
    """解析 pytest junitxml 输出。

    Returns:
        {"passed": int, "failed": int, "failed_tests": [str]}
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()

    passed = 0
    failed_tests: list[str] = []

    for tc in root.iter("testcase"):
        has_failure = any(child.tag in ("failure", "error") for child in tc)
        if has_failure:
            cls = tc.attrib.get("classname", "")
            name = tc.attrib.get("name", "")
            failed_tests.append(f"{cls}::{name}")
        else:
            passed += 1

    return {
        "passed": passed,
        "failed": len(failed_tests),
        "failed_tests": failed_tests,
    }
