import requests, os
from cryptography.fernet import Fernet

# 使用与服务器相同的密钥
SECRET_KEY = b"bExE48Yv_secIarHXuvgy4KNW9_jFbePgaq_D0MmzV4="  # 使用生成的32位密钥
fernet = Fernet(SECRET_KEY)


def upload_file(url, file_path):
    with open(file_path, "rb") as file:
        file_data = file.read()
        encrypted_data = fernet.encrypt(file_data)

    files = {"file": (os.path.basename(file_path), encrypted_data)}
    response = requests.post(url, files=files)

    if response.status_code == 200:
        print("File uploaded successfully")
    else:
        print("Failed to upload file:", response.status_code)


def download_file(url, save_path):
    response = requests.get(url)

    if response.status_code == 200:
        encrypted_data = response.content
        file_data = fernet.decrypt(encrypted_data)

        with open(save_path, "wb") as f:
            f.write(file_data)
        print(f"File downloaded and saved as {save_path}")
    else:
        print("Failed to download file:", response.status_code)


# 示例使用
upload_file("http://127.0.0.1:4443/upload", "README.md")
download_file("http://127.0.0.1:4443/send_files/README.md", "downloaded_README.md")
