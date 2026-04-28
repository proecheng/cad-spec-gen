"""发布版本元数据一致性契约。"""

from __future__ import annotations

import json
import re
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[1]


def _pyproject_version() -> str:
    pyproject = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    try:
        import tomllib
    except ModuleNotFoundError:
        version = re.search(r'(?m)^version = "([^"]+)"$', pyproject)
        assert version, "pyproject.toml 缺少 project version"
        return version.group(1)

    data = tomllib.loads(pyproject)
    return data["project"]["version"]


def test_release_version_metadata_uses_pyproject_single_source():
    """所有用户可见版本号必须跟 pyproject.toml 一致。"""
    expected = _pyproject_version()

    init_text = (_ROOT / "src" / "cad_spec_gen" / "__init__.py").read_text(
        encoding="utf-8"
    )
    assert f'__version__ = "{expected}"' in init_text

    for rel in ("skill.json", "src/cad_spec_gen/data/skill.json"):
        data = json.loads((_ROOT / rel).read_text(encoding="utf-8"))
        assert data["version"] == expected, rel

    marker = json.loads((_ROOT / ".cad_skill_version.json").read_text(encoding="utf-8"))
    assert marker["version"] == expected

    readme = (_ROOT / "README.md").read_text(encoding="utf-8")
    assert f"**Latest: v{expected}**" in readme

    changelog = (_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    top_release = re.search(r"^## \[v([^\]]+)\]", changelog, re.MULTILINE)
    assert top_release, "CHANGELOG.md 缺少顶部 release 标题"
    assert top_release.group(1) == expected
