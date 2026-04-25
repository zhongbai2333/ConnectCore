from __future__ import annotations

import os
import json
from typing import Any

import yaml  # type: ignore[import-untyped]
import zipfile
from pathlib import Path

try:
    from mcdreforged.api.all import ServerInterface
except ImportError:
    pass

from connect_core.context import GlobalContext


class YmlLanguage:
    def __init__(self, path: str | Path, sid: str, lang: str = "en_us") -> None:
        self.full_path = str(path)
        self.path, self.filename = os.path.split(str(path))
        self.sid = sid
        self.lang_file = self._read_yaml(lang)

    # 读取yaml
    def _read_yaml(self, lang: str = "en_us") -> dict[str, Any]:
        if zipfile.is_zipfile(self.full_path):
            try:
                with zipfile.ZipFile(self.full_path, "r") as pyz:
                    with pyz.open(f"lang/{lang}.yml") as f:
                        config_data = f.read().decode("utf-8")
                        result: dict[str, Any] = yaml.safe_load(config_data) or {}
                        return result
            except KeyError:
                # 归档中没有对应语言文件：插件可选语言文件，返回空字典
                return {}
        else:
            target = Path(self.path) / "lang" / f"{lang}.yml"
            if not target.exists():
                # 目录形式插件缺少语言文件：返回空字典
                return {}
            with target.open("r", encoding="utf-8") as f:
                data: dict[str, Any] = (
                    yaml.load(stream=f, Loader=yaml.FullLoader) or {}
                )
                return data

    def _get_nested_value(
        self, data: Any, keys_path: list[str], default: Any = None
    ) -> Any:
        for key in keys_path:
            if isinstance(data, dict) and key in data:
                data = data[key]
            else:
                return default
        return data

    def translate(self, key: str, *args: Any) -> str:
        """获取翻译"""
        if GlobalContext.is_mcdr_mode():
            result = ServerInterface.si().tr(f"{self.sid}." + key, *args)
            return str(result) if result is not None else key
        else:
            key_path = (f"{self.sid}." + key).split(".")
            translation = self._get_nested_value(self.lang_file, key_path)
            if translation is None:
                return key
            if not isinstance(translation, str):
                translation = str(translation)
            return translation.format(*args)


def get_version(path: str | Path = GlobalContext.get_path()) -> str:
    """获取当前版本号"""
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path, "r") as pyz:
            with pyz.open("mcdreforged.plugin.json") as f:
                result: str = json.load(f).get("version", "unknown")
                return result
    else:
        with open(
            f"{Path(path).parent}/mcdreforged.plugin.json", "r", encoding="utf-8"
        ) as f:
            result2: str = json.load(f).get("version", "unknown")
            return result2
