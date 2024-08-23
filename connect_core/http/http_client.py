import os
import requests
from connect_core.aes_encrypt import aes_encrypt, aes_decrypt
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from connect_core.interface.control_interface import CoreControlInterface


def upload_file(
    control_interface: "CoreControlInterface", url: str, file_path: str
) -> int:
    """
    上传文件到指定URL，并在上传前对文件进行RSA加密。

    Args:
        url (str): 目标服务器的URL。
        file_path (str): 本地文件的路径。

    Returns:
        int: HTTP响应状态码，200表示成功，否则返回相应的错误码。
    """
    try:
        with open(file_path, "rb") as file:
            file_data = file.read()
            encrypted_data = aes_encrypt(file_data)

        files = {"file": (os.path.basename(file_path), encrypted_data)}
        response = requests.post(url, files=files)

        return response.status_code
    except FileNotFoundError:
        control_interface.error(f"File not found: {file_path}")
        return 404
    except Exception as e:
        control_interface.error(f"An error occurred: {e}")
        return 500


def download_file(
    control_interface: "CoreControlInterface", url: str, save_path: str
) -> int:
    """
    从指定URL下载文件，并在保存前对文件进行RSA解密。

    Args:
        url (str): 文件下载的URL。
        save_path (str): 下载后保存文件的路径。

    Returns:
        int: HTTP响应状态码，200表示成功，400表示解密错误，否则返回相应的错误码。
    """
    try:
        response = requests.get(url)

        if response.status_code == 200:
            encrypted_data = response.content
            try:
                file_data = aes_decrypt(encrypted_data)

                with open(save_path, "wb") as file:
                    file.write(file_data)
                return 200
            except Exception as e:
                control_interface.error(f"Decryption error: {e}")
                return 400
        else:
            return response.status_code
    except Exception as e:
        control_interface.error(f"An error occurred: {e}")
        return 500
