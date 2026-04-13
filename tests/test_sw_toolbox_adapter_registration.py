"""default_resolver 集成 SwToolboxAdapter 的注册测试（SW-B6）。"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestSwToolboxRegistration:
    """v4 §3.1: SwToolboxAdapter 必须在 bd_warehouse 之后注册（依赖 bd_warehouse）。
    Dispatch 优先级由 yaml mappings 控制，不依赖注册顺序。
    """

    def test_default_resolver_registers_sw_toolbox_adapter(self, tmp_path):
        """default_resolver 返回的 PartsResolver 应含名为 'sw_toolbox' 的 adapter。"""
        from parts_resolver import default_resolver

        resolver = default_resolver(project_root=str(tmp_path))
        adapter_names = [a.name for a in resolver.adapters]
        assert "sw_toolbox" in adapter_names

    def test_sw_toolbox_registered_after_bd_warehouse(self, tmp_path):
        """注册顺序：bd_warehouse → sw_toolbox（前者先注册，确保依赖可用）。"""
        from parts_resolver import default_resolver

        resolver = default_resolver(project_root=str(tmp_path))
        names = [a.name for a in resolver.adapters]
        if "bd_warehouse" in names and "sw_toolbox" in names:
            assert names.index("sw_toolbox") > names.index("bd_warehouse")

    def test_sw_toolbox_receives_config_from_yaml(self, tmp_path):
        """yaml `solidworks_toolbox:` 段应作为 config 传入 SwToolboxAdapter。
        当前 default yaml 还没有该段（Task 6 才加），故 config 应为 {}。"""
        from parts_resolver import default_resolver

        resolver = default_resolver(project_root=str(tmp_path))
        sw_adapter = next(
            (a for a in resolver.adapters if a.name == "sw_toolbox"), None
        )
        assert sw_adapter is not None
        # 现阶段 default yaml 无 solidworks_toolbox 段，config 应为 {}
        assert sw_adapter.config == {}
