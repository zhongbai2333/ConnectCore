import sys, os, hashlib


def restart_program():
    """
    重启程序，使用当前的Python解释器重新执行当前脚本。
    """
    python = sys.executable
    os.execl(python, python, *sys.argv)


def check_file_exists(file_path):
    """
    检查目录中的特定文件是否存在。

    Args:
        file_path (str): 文件路径

    Returns:
        bool: 如果文件存在则返回 True，否则返回 False
    """

    # 检查文件是否存在且是一个文件
    return os.path.isfile(file_path)


def get_file_hash(file_path, algorithm="sha256"):
    """
    获取文件的哈希值。

    Args:
        file_path (str): 文件路径
        algorithm (str): 哈希算法，默认使用 'sha256'

    Returns:
        str: 文件的哈希值，如果文件不存在则返回 None
    """
    try:
        hash_func = hashlib.new(algorithm)

        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_func.update(chunk)

        return hash_func.hexdigest()
    except (IOError, OSError) as e:
        print(f"计算哈希值时出错: {e}")
        return None
    except ValueError as e:
        print(f"不支持的哈希算法: {e}")
        return None


def verify_file_hash(file_path, expected_hash, algorithm="sha256"):
    """
    验证文件的哈希值。

    Args:
        file_path (str): 文件路径
        expected_hash (str): 预期的哈希值
        algorithm (str): 哈希算法，默认使用 'sha256'

    Returns:
        bool: 如果哈希值匹配则返回 True，否则返回 False
    """
    actual_hash = get_file_hash(file_path, algorithm)

    if actual_hash is None:
        print("无法获取文件的哈希值。")
        return False

    return actual_hash == expected_hash


def append_to_path(path, filename):
    """
    Appends a filename to the given path if it is a directory.

    :param path: The path to check and modify.
    :param filename: The filename to append if path is a directory.
    :return: The modified path.
    """
    if os.path.isdir(path):
        return os.path.join(path, filename)
    return path
