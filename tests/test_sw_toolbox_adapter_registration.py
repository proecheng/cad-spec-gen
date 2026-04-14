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
        """yaml `solidworks_toolbox:` 段应作为 config 传入 SwToolboxAdapter。"""
        from parts_resolver import default_resolver

        resolver = default_resolver(project_root=str(tmp_path))
        sw_adapter = next(
            (a for a in resolver.adapters if a.name == "sw_toolbox"), None
        )
        assert sw_adapter is not None
        # default yaml 应至少含 min_score 字段（Task 6 已加 solidworks_toolbox 段）
        assert sw_adapter.config.get("min_score") == 0.30

    def test_sw_toolbox_rejects_malformed_size_patterns(self, tmp_path, monkeypatch):
        """yaml size_patterns 非 dict 时，adapter 注册被拒绝但管道继续。"""
        from parts_resolver import default_resolver

        # monkeypatch load_registry 返回带恶意 size_patterns 的配置
        def fake_load_registry(*args, **kwargs):
            return {
                "solidworks_toolbox": {
                    "size_patterns": "malformed_should_be_dict",  # 非 dict
                },
                "mappings": [],
            }

        monkeypatch.setattr("parts_resolver.load_registry", fake_load_registry)

        # 不应抛异常，应静默不注册 sw_toolbox
        resolver = default_resolver(project_root=str(tmp_path))
        adapter_names = [a.name for a in resolver.adapters]
        assert "sw_toolbox" not in adapter_names
        # 其他 adapter 应正常注册（管道继续）
        assert "jinja_primitive" in adapter_names


class TestDefaultYamlConfig:
    """v4 §6: parts_library.default.yaml 的 solidworks_toolbox 段内容。"""

    def test_default_yaml_provides_solidworks_toolbox_section(self, tmp_path):
        from parts_resolver import default_resolver

        resolver = default_resolver(project_root=str(tmp_path))
        sw_adapter = next(a for a in resolver.adapters if a.name == "sw_toolbox")
        cfg = sw_adapter.config

        assert cfg.get("enabled") == "auto"
        assert set(cfg.get("standards", [])) >= {"GB", "ISO", "DIN"}
        assert cfg.get("min_score") == 0.30

        # token_weights 四字段齐全（决策 #12）
        weights = cfg.get("token_weights", {})
        assert weights == {
            "part_no": 2.0,
            "name_cn": 1.0,
            "material": 0.5,
            "size": 1.5,
        }

        # size_patterns 两个类别齐全（决策 #9 + §1.3）
        sp = cfg.get("size_patterns", {})
        assert "fastener" in sp
        assert "bearing" in sp
        # fastener 含 exclude_patterns 防 UNC/Tr/G/NPT
        assert any("UN" in p for p in sp["fastener"].get("exclude_patterns", []))

        # com 超时常量可覆盖
        com_cfg = cfg.get("com", {})
        assert com_cfg.get("cold_start_timeout_sec") == 90
        assert com_cfg.get("restart_every_n_converts") == 50

    def test_default_yaml_has_gb_fastener_rule_before_generic_fallback(self, tmp_path):
        """YAML mapping: GB 高优先级规则必须在 jinja_primitive 兜底之前。"""
        from parts_resolver import load_registry

        reg = load_registry(str(tmp_path))
        mappings = reg.get("mappings", [])
        sw_gb_idx = None
        bd_any_idx = None
        for i, m in enumerate(mappings):
            if m.get("adapter") == "sw_toolbox":
                keywords = m.get("match", {}).get("keyword_contains", [])
                if any("GB" in k for k in keywords) and sw_gb_idx is None:
                    sw_gb_idx = i
            if m.get("adapter") == "jinja_primitive" and bd_any_idx is None:
                bd_any_idx = i

        assert sw_gb_idx is not None, "缺少 SW Toolbox GB 规则"
        assert bd_any_idx is not None, "缺少 jinja_primitive 兜底"
        assert sw_gb_idx < bd_any_idx, "GB 规则必须在 jinja_primitive 兜底之前"

    def test_iso_din_bearing_rule_before_bd_warehouse_generic(self, tmp_path):
        """v4 §6 ordering: SW ISO/DIN bearing 必须在 bd_warehouse 通用 bearing 兜底之前。
        否则 first-hit-wins 下 bd_warehouse {category: bearing} 抢先，SW 永不命中。
        """
        from parts_resolver import load_registry

        reg = load_registry(str(tmp_path))
        mappings = reg.get("mappings", [])
        sw_iso_bearing_idx = None
        bd_generic_bearing_idx = None
        for i, m in enumerate(mappings):
            if m.get("adapter") == "sw_toolbox":
                spec = m.get("spec", {})
                std = spec.get("standard")
                # standard 可为 list 或 str
                if isinstance(std, list) and "ISO" in std and \
                        spec.get("part_category") == "bearing":
                    sw_iso_bearing_idx = sw_iso_bearing_idx or i
            if m.get("adapter") == "bd_warehouse" and \
                    m.get("match") == {"category": "bearing"} and \
                    bd_generic_bearing_idx is None:
                bd_generic_bearing_idx = i

        assert sw_iso_bearing_idx is not None, "缺少 SW Toolbox ISO/DIN bearing 规则"
        assert bd_generic_bearing_idx is not None, "缺少 bd_warehouse 通用 bearing 兜底"
        assert sw_iso_bearing_idx < bd_generic_bearing_idx, (
            "SW ISO/DIN bearing 必须在 bd_warehouse 通用 bearing 兜底之前"
        )
