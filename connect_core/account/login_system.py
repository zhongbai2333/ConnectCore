import json
from connect_core.tools import decode_base64

def analyze_password(key: str) -> dict:
    """
    解析初始化密钥

    Args:
        key (str): 密钥
    :return: 初始化字典
    """
    data = json.loads(decode_base64(key))
    return data
