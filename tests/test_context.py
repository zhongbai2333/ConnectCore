"""Tests for connect_core.context — GlobalContext DI refactoring."""

from __future__ import annotations

import pytest
from connect_core.context import GlobalContext, _ContextState


@pytest.fixture(autouse=True)
def _reset_context():
    """Ensure every test starts with a clean GlobalContext state."""
    GlobalContext.reset()
    yield
    GlobalContext.reset()


class TestContextState:
    """Test the internal _ContextState dataclass."""

    def test_defaults(self):
        state = _ContextState()
        assert state.debug_mode is False
        assert state.debug_level == 0
        assert state.server_mode is False
        assert state.mcdr_mode is False
        assert state.mcdr_core is None

    def test_custom_values(self):
        state = _ContextState(debug_mode=True, debug_level=3, server_mode=True)
        assert state.debug_mode is True
        assert state.debug_level == 3
        assert state.server_mode is True


class TestGlobalContextInit:
    """Test GlobalContext constructor debug parsing logic."""

    def test_default_no_debug(self):
        GlobalContext()
        assert GlobalContext.is_debug_mode() is False
        assert GlobalContext.get_debug_level() == 0

    def test_debug_bool_true(self):
        GlobalContext(debug=True)
        assert GlobalContext.is_debug_mode() is True
        assert GlobalContext.get_debug_level() == 1

    def test_debug_bool_false(self):
        GlobalContext(debug=False)
        assert GlobalContext.is_debug_mode() is False
        assert GlobalContext.get_debug_level() == 0

    def test_debug_int_positive(self):
        GlobalContext(debug=3)
        assert GlobalContext.is_debug_mode() is True
        assert GlobalContext.get_debug_level() == 3

    def test_debug_int_zero(self):
        GlobalContext(debug=0)
        assert GlobalContext.is_debug_mode() is False
        assert GlobalContext.get_debug_level() == 0

    def test_debug_negative_clamped(self):
        GlobalContext(debug=-5)
        assert GlobalContext.get_debug_level() == 0
        assert GlobalContext.is_debug_mode() is False

    def test_debug_non_numeric_truthy(self):
        GlobalContext(debug="yes")
        assert GlobalContext.is_debug_mode() is True
        assert GlobalContext.get_debug_level() == 1

    def test_debug_none(self):
        GlobalContext(debug=None)
        assert GlobalContext.is_debug_mode() is False
        assert GlobalContext.get_debug_level() == 0

    def test_server_mode(self):
        GlobalContext(server=True)
        assert GlobalContext.is_server_mode() is True

    def test_mcdr_mode(self):
        sentinel = object()
        GlobalContext(mcdr=True, mcdr_interface=sentinel)
        assert GlobalContext.is_mcdr_mode() is True
        assert GlobalContext.get_mcdr_core() is sentinel


class TestGlobalContextPaths:
    """Test path resolution methods."""

    def test_get_path_returns_path(self):
        from pathlib import Path
        result = GlobalContext.get_path()
        assert isinstance(result, Path)

    def test_get_config_path_cli_mode(self):
        GlobalContext(server=False, mcdr=False)
        cfg = GlobalContext.get_config_path()
        assert cfg.name == "config.yml"
        assert "connect_core" not in str(cfg)

    def test_get_config_path_mcdr_mode(self):
        GlobalContext(mcdr=True)
        cfg = GlobalContext.get_config_path()
        assert "config/connect_core/config.yml" in str(cfg).replace("\\", "/")


class TestGlobalContextReset:
    """Test the reset() and get_state() helper methods."""

    def test_reset_clears_state(self):
        GlobalContext(debug=5, server=True, mcdr=True)
        assert GlobalContext.is_debug_mode() is True
        GlobalContext.reset()
        assert GlobalContext.is_debug_mode() is False
        assert GlobalContext.get_debug_level() == 0
        assert GlobalContext.is_server_mode() is False
        assert GlobalContext.is_mcdr_mode() is False
        assert GlobalContext.get_mcdr_core() is None

    def test_get_state_returns_internal(self):
        GlobalContext(debug=2, server=True)
        state = GlobalContext.get_state()
        assert isinstance(state, _ContextState)
        assert state.debug_level == 2
        assert state.server_mode is True

    def test_state_is_singleton(self):
        s1 = GlobalContext.get_state()
        GlobalContext(debug=1)
        s2 = GlobalContext.get_state()
        assert s1 is s2


class TestGlobalContextOverwrite:
    """Test that re-initialization properly overwrites previous state."""

    def test_reinit_overwrites(self):
        GlobalContext(debug=5, server=True)
        assert GlobalContext.get_debug_level() == 5
        assert GlobalContext.is_server_mode() is True

        GlobalContext(debug=0, server=False)
        assert GlobalContext.get_debug_level() == 0
        assert GlobalContext.is_server_mode() is False
