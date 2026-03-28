"""Tests for BaseConfig YAML-backed configuration system."""

from __future__ import annotations

from pathlib import Path

import pytest

from connect_core.tools.base_config import (
    BaseConfig,
    ConfigError,
    ConfigTypeError,
    ConfigValidationError,
    Field,
)


class TestField:
    def test_field_defaults(self):
        f = Field(default=42, description="a number")
        assert f.default == 42
        assert f.description == "a number"

    def test_field_no_description(self):
        f = Field(default="x")
        assert f.description == ""


class TestBaseConfigLoad:
    def test_load_creates_default_file(self, tmp_path: Path, sample_config_class):
        cfg_path = str(tmp_path / "cfg.yml")
        cfg = sample_config_class.load(config_path=cfg_path)
        assert cfg.name == "test"
        assert cfg.port == 8080
        assert Path(cfg_path).exists()

    def test_load_reads_existing(self, tmp_path: Path, sample_config_class):
        cfg_path = tmp_path / "cfg.yml"
        cfg_path.write_text("name: custom\nport: 9090\n", encoding="utf-8")
        cfg = sample_config_class.load(config_path=str(cfg_path))
        assert cfg.name == "custom"
        assert cfg.port == 9090

    def test_load_fills_missing_fields(self, tmp_path: Path, sample_config_class):
        cfg_path = tmp_path / "cfg.yml"
        cfg_path.write_text("name: partial\n", encoding="utf-8")
        cfg = sample_config_class.load(config_path=str(cfg_path))
        assert cfg.name == "partial"
        assert cfg.port == 8080  # filled from default


class TestBaseConfigSave:
    def test_save_and_reload(self, tmp_path: Path, sample_config_class):
        cfg_path = str(tmp_path / "out.yml")
        cfg = sample_config_class(config_path=cfg_path, name="saved", port=1234)
        cfg.save()
        reloaded = sample_config_class.load(config_path=cfg_path)
        assert reloaded.name == "saved"
        assert reloaded.port == 1234

    def test_save_creates_parent_dirs(self, tmp_path: Path, sample_config_class):
        cfg_path = str(tmp_path / "sub" / "dir" / "cfg.yml")
        cfg = sample_config_class(config_path=cfg_path)
        cfg.save()
        assert Path(cfg_path).exists()


class TestBaseConfigValidation:
    def test_type_error_on_wrong_type(self, sample_config_class):
        with pytest.raises(ConfigTypeError):
            sample_config_class(port="not_a_number")

    def test_setattr_type_check(self, sample_config_class):
        cfg = sample_config_class()
        with pytest.raises(ConfigTypeError):
            cfg.port = "bad"

    def test_update_valid(self, sample_config_class):
        cfg = sample_config_class()
        cfg.update(name="updated", port=3000)
        assert cfg.name == "updated"
        assert cfg.port == 3000

    def test_update_invalid_key(self, sample_config_class):
        cfg = sample_config_class()
        with pytest.raises(ConfigError):
            cfg.update(nonexistent=1)

    def test_load_wrong_type_raises(self, tmp_path: Path, sample_config_class):
        cfg_path = tmp_path / "bad.yml"
        cfg_path.write_text("name: ok\nport: not_int\n", encoding="utf-8")
        with pytest.raises(ConfigTypeError):
            sample_config_class.load(config_path=str(cfg_path))


class TestCheckType:
    def test_plain_type(self):
        assert BaseConfig._check_type(42, int) is True
        assert BaseConfig._check_type("x", int) is False

    def test_list_type(self):
        from typing import List

        assert BaseConfig._check_type([1, 2], List[int]) is True
        assert BaseConfig._check_type([1, "a"], List[int]) is False

    def test_dict_type(self):
        from typing import Dict

        assert BaseConfig._check_type({"a": 1}, Dict[str, int]) is True
        assert BaseConfig._check_type({"a": "b"}, Dict[str, int]) is False

    def test_union_type(self):
        from typing import Union

        assert BaseConfig._check_type(42, Union[int, str]) is True
        assert BaseConfig._check_type("x", Union[int, str]) is True
        assert BaseConfig._check_type([], Union[int, str]) is False
