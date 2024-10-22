import http.server
from socketserver import ThreadingMixIn
import os
from urllib.parse import urlparse
import cgi
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from connect_core.interface.control_interface import CoreControlInterface

from connect_core.aes_encrypt import aes_encrypt, aes_decrypt


def http_main(control_interface: "CoreControlInterface"):
    class ThreadingHTTPServer(ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True

    class SimpleHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            parsed_path = urlparse(self.path)
            # 确保路径从send_files目录中获取文件
            file_path = parsed_path.path.replace("/send_files/", "", 1)
            if os.path.isfile(file_path):
                path, _ = os.path.split(file_path)
                with open(file_path, "rb") as f:
                    file_data = f.read()
                encrypted_data = aes_encrypt(file_data, path)

                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header(
                    "Content-Disposition",
                    f'attachment; filename="{os.path.basename(file_path)}"',
                )
                self.send_header("Content-Length", str(len(encrypted_data)))
                self.end_headers()
                self.wfile.write(encrypted_data)
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"File not found")

        def do_POST(self):
            content_type, pdict = cgi.parse_header(self.headers["Content-Type"])
            if content_type == "multipart/form-data":
                pdict["boundary"] = bytes(pdict["boundary"], "utf-8")
                form = cgi.FieldStorage(
                    fp=self.rfile,
                    headers=self.headers,
                    environ={"REQUEST_METHOD": "POST"},
                    keep_blank_values=True,
                )

                # 获取上传的文件
                if "file" in form:
                    field_item = form["file"]
                    account = form["account"]
                    encrypted_data = field_item.file.read()

                    # 解密文件数据
                    try:
                        file_data = aes_decrypt(
                            encrypted_data,
                            control_interface.get_config("account.json")[account],
                        )
                    except Exception as e:
                        self.send_response(400)
                        self.end_headers()
                        self.wfile.write(b"Failed to decrypt file")
                        return

                    # 提取文件名
                    filename = field_item.filename
                    if not filename:
                        self.send_response(400)
                        self.end_headers()
                        self.wfile.write(
                            b"Missing filename in Content-Disposition header"
                        )
                        return

                    # 确保保存目录存在
                    save_dir = "received_files"
                    os.makedirs(save_dir, exist_ok=True)

                    # 保存文件
                    file_path = os.path.join(save_dir, filename)
                    with open(file_path, "wb") as f:
                        f.write(file_data)

                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"File received and saved successfully")
                else:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"No file part in request")
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Invalid Content-Type")

        def log_message(self, format, *args):
            control_interface.info(f"[HTTP] [{self.address_string()}] {format % args}")

    def run(server_class=ThreadingHTTPServer, handler_class=SimpleHTTPRequestHandler):
        config = control_interface.get_config()
        server_address = (config["ip"], config["http_port"])
        httpd = server_class(server_address, handler_class)
        if not os.path.exists("send_files/"):
            os.makedirs("send_files/")
        control_interface.info(
            control_interface.tr("net_core.service.start_http").format(
                f"{server_address[0]}:{server_address[1]}"
            )
        )
        httpd.serve_forever()

    run()
