"""Shared pytest fixtures for ConnectCore tests."""

import tempfile
from pathlib import Path

import pytest

from connect_core.tools.base_config import BaseConfig, Field


@pytest.fixture()
def tmp_dir(tmp_path: Path) -> Path:
    """Provide a clean temporary directory for each test."""
    return tmp_path


@pytest.fixture()
def sample_config_class():
    """Create a minimal BaseConfig subclass for testing."""

    class SampleConfig(BaseConfig):
        __config_path__: str = "test_config.yml"
        name: str = Field(default="test", description="Name of the test config")
        port: int = Field(default=8080, description="Port number")

    return SampleConfig
