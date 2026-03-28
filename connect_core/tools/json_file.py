from __future__ import annotations

import os
import json
from typing import Dict, Any


class JsonDataEditor:
    def __init__(self, filepath: str) -> None:
        self.filepath = filepath
        # 检查文件是否存在，如果不存在则创建空的JSON文件
        if not os.path.exists(filepath):
            path, _ = os.path.split(filepath)
            if path != "." and path:
                os.makedirs(
                    path, exist_ok=True
                )  # 使用 exist_ok=True 避免 FileExistsError
            self._write_data()

    def _read_data(self) -> Dict[str, Any]:
        """读取 JSON 文件内容并返回一个字典，如果内容无效则重置并返回空字典"""
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data: Dict[str, Any] = json.load(f)
                return data
        except (json.JSONDecodeError, FileNotFoundError):
            # 文件为空、格式错误或突然被删了：重置为 {} 并写回磁盘
            print(f"Json File {self.filepath} Can't Read!")
            return {}

    def _write_data(self, data: Dict[str, Any] = {}) -> None:
        """将字典写入 JSON 文件"""
        with open(self.filepath, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=4)

    def read(self) -> Dict[str, Any]:
        """获取当前 JSON 文件中的数据"""
        return self._read_data()

    def write(self, config: Dict[str, Any]) -> None:
        """向 JSON 文件中添加新的数据项"""
        global global_data_json
        self._write_data(config)
