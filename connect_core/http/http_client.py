import requests, os

from connect_core.rsa_encrypt import rsa_encrypt, rsa_decrypt


def upload_file(url: str, file_path: str) -> int:
    with open(file_path, "rb") as file:
        file_data = file.read()
        encrypted_data = rsa_encrypt(file_data)

    files = {"file": (os.path.basename(file_path), encrypted_data)}
    response = requests.post(url, files=files)

    if response.status_code == 200:
        return 200
    else:
        return response.status_code


def download_file(url: str, save_path: str) -> int:
    response = requests.get(url)

    if response.status_code == 200:
        encrypted_data = response.content
        try:
            file_data = rsa_decrypt(encrypted_data)

            with open(save_path, "wb") as f:
                f.write(file_data)
            return 200
        except Exception:
            return 400
    else:
        return response.status_code