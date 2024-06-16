import logging
from flask import Flask, send_file

app = Flask(__name__)


@app.route("/download-pem")
def download_pem():
    return send_file("certs/server.pem", as_attachment=True)


def https_main():
    # 禁用特定的警告信息
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)

    app.run(
        host="0.0.0.0", port=443, ssl_context=("certs/server.crt", "certs/server.key")
    )
