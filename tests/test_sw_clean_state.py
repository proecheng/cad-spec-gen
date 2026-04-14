"""sw_b9 clean state 工具测试。"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestCleanSwState:
    def test_quits_session_when_provided(self):
        from tools.sw_b9_clean_state import clean_sw_state

        session = MagicMock()
        with patch("tools.sw_b9_clean_state._wait_sldworks_gone", return_value=True):
            clean_sw_state(session=session, step_cache_dir=None)
        session.quit.assert_called_once()

    def test_waits_for_sldworks_gone(self):
        from tools.sw_b9_clean_state import clean_sw_state

        with patch("tools.sw_b9_clean_state._wait_sldworks_gone") as w:
            w.return_value = True
            clean_sw_state(session=None, step_cache_dir=None)
            w.assert_called_once()

    def test_raises_on_lingering_sldworks(self):
        from tools.sw_b9_clean_state import clean_sw_state, SwStateNotClean

        with patch("tools.sw_b9_clean_state._wait_sldworks_gone", return_value=False):
            try:
                clean_sw_state(session=None, step_cache_dir=None, raise_on_lingering=True)
                assert False, "应抛 SwStateNotClean"
            except SwStateNotClean:
                pass

    def test_clears_step_cache_dir(self, tmp_path):
        from tools.sw_b9_clean_state import clean_sw_state

        cache = tmp_path / "sw_toolbox"
        cache.mkdir()
        (cache / "foo.step").write_text("x")
        with patch("tools.sw_b9_clean_state._wait_sldworks_gone", return_value=True):
            clean_sw_state(session=None, step_cache_dir=cache)
        assert not (cache / "foo.step").exists()
        assert cache.exists()  # 目录保留，只清内容
