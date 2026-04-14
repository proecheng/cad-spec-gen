"""sw_b9 junit xml parser 测试。"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


SAMPLE_XML = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="3" failures="1" errors="0" skipped="0">
    <testcase classname="tests.test_foo" name="test_a"/>
    <testcase classname="tests.test_foo" name="test_b"/>
    <testcase classname="tests.test_bar" name="test_c">
      <failure message="assertion failed">stack trace</failure>
    </testcase>
  </testsuite>
</testsuites>
"""


class TestParseJunitXml:
    def test_counts_passed_failed(self, tmp_path):
        from tools.sw_b9_junit_parser import parse_junit_xml

        xml = tmp_path / "out.xml"
        xml.write_text(SAMPLE_XML, encoding="utf-8")

        result = parse_junit_xml(xml)
        assert result["passed"] == 2
        assert result["failed"] == 1
        assert result["failed_tests"] == ["tests.test_bar::test_c"]

    def test_empty_xml_returns_zeros(self, tmp_path):
        from tools.sw_b9_junit_parser import parse_junit_xml

        xml = tmp_path / "empty.xml"
        xml.write_text('<?xml version="1.0"?><testsuites/>', encoding="utf-8")
        result = parse_junit_xml(xml)
        assert result == {"passed": 0, "failed": 0, "failed_tests": []}
