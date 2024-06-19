import http.server, ssl, os, cgi
from socketserver import ThreadingMixIn
from urllib.parse import urlparse

from connect_core.cli.log_system import info_print
from connect_core.cli.get_config_translate import translate, config


global ALLOWED_KEY, IP, PORT


class ThreadingHTTPServer(ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


class SimpleHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def _verify_key(self):
        # 从头部获取密钥
        key = self.headers.get("X-API-KEY")
        if key == ALLOWED_KEY:
            return True
        else:
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b"Forbidden: Invalid API Key")
            return False

    def do_GET(self):
        if not self._verify_key():
            return

        parsed_path = urlparse(self.path)
        file_path = parsed_path.path.lstrip("/")
        if os.path.isfile(file_path):
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header(
                "Content-Disposition",
                f'attachment; filename="{os.path.basename(file_path)}"',
            )
            self.end_headers()
            with open(file_path, "rb") as f:
                self.wfile.write(f.read())
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"File not found")

    def do_POST(self):
        if not self._verify_key():
            return

        # 解析multipart/form-data
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
                file_data = field_item.file.read()

                # 提取文件名
                filename = field_item.filename
                if not filename:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"Missing filename in Content-Disposition header")
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


def run(server_class=ThreadingHTTPServer, handler_class=SimpleHTTPRequestHandler):
    server_address = (IP, PORT)
    httpd = server_class(server_address, handler_class)

    # 创建SSL上下文
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile="certs/server.crt", keyfile="certs/server.key")

    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    info_print(
        translate()["connect_core"]["cli"]["service"]["start_https"].format(
            f"{IP}:{PORT}"
        )
    )
    httpd.serve_forever()


def https_main():
    global ALLOWED_KEY, IP, PORT
    IP = config()["ip"]
    PORT = config()["https_port"]
    ALLOWED_KEY = config()["password"]
    if not os.path.exists("send_files/"):
        os.makedirs("send_files/")
    run()
