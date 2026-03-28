import binascii
import json
from typing import Any
from connect_core.tools.tools import decode_base64


def analyze_password(key: str) -> dict[str, Any] | None:
    """
    解析初始化密钥

    Args:
        key (str): 密钥
    :return: 初始化字典
    """
    if not key or len(key) > 4096:
        return None
    try:
        data: dict[str, Any] = json.loads(decode_base64(key))
        return data
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError, binascii.Error):
        return None
