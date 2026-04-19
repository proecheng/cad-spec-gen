"""Task 6：UNC 路径可达性校验测试。

区分三种状态：
- 'ok'：路径存在且可读
- 'invalid'：本地路径不存在（用户配置错误）
- 'not_accessible'：UNC 路径不可达（网络/权限问题）
"""

from __future__ import annotations


def test_unc_unreachable_returns_not_accessible_diagnosis(monkeypatch):
    from adapters.solidworks.sw_detect import probe_toolbox_path_reachability

    # UNC 路径但服务器不存在 → 应归类为网络不可达
    result = probe_toolbox_path_reachability(r"\\fileserver-doesnotexist\Toolbox")
    assert result == "not_accessible"


def test_local_path_invalid_returns_invalid(monkeypatch):
    from adapters.solidworks.sw_detect import probe_toolbox_path_reachability

    result = probe_toolbox_path_reachability("C:/this/path/does/not/exist")
    assert result == "invalid"


def test_local_path_valid_returns_ok(tmp_path):
    from adapters.solidworks.sw_detect import probe_toolbox_path_reachability

    result = probe_toolbox_path_reachability(str(tmp_path))
    assert result == "ok"
