import requests, os


def send(url, file_path, api_key):
    url = "https://127.0.0.1:4443"
    file_path = "README.md"
    api_key = "WH6EyoA50k"  # 正确的API密钥

    with open(file_path, "rb") as f:
        files = {"file": f}
        headers = {"X-API-KEY": api_key}
        response = requests.post(
            url, files=files, headers=headers, verify=False
        )  # Set verify=True for real certificates
        print(response.text)


def recve(url, api_key, path):
    url = "https://127.0.0.1:4443/LICENSE"
    api_key = "WH6EyoA50k"  # 正确的API密钥

    headers = {"X-API-KEY": api_key}
    response = requests.get(
        url, headers=headers, verify=False
    )  # Set verify=True for real certificates

    if response.status_code == 200:
        # 从响应头中提取文件名
        content_disposition = response.headers.get("Content-Disposition")
        if content_disposition:
            filename = content_disposition.split("filename=")[-1].strip('"')
        else:
            # 默认文件名
            filename = "downloaded_file"

        save_path = os.path.join(path, filename)

        # 确保保存目录存在
        os.makedirs(path, exist_ok=True)

        # 保存文件
        with open(save_path, "wb") as f:
            f.write(response.content)
        print(f"File downloaded successfully as {filename}")
    else:
        print("Failed to download file:", response.status_code)
