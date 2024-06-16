import os
from OpenSSL import crypto


def create_ssl_key(ip: str, path="certs/"):
    if not os.path.exists(path):
        os.makedirs(path)
    # 生成私钥
    key = crypto.PKey()
    key.generate_key(crypto.TYPE_RSA, 2048)

    # 创建自签名证书
    cert = crypto.X509()
    cert.get_subject().CN = ip  # 替换为服务器的IP地址或域名
    cert.set_serial_number(1000)
    cert.gmtime_adj_notBefore(0)
    cert.gmtime_adj_notAfter(365 * 24 * 60 * 60)  # 证书有效期1年
    cert.set_issuer(cert.get_subject())
    cert.set_pubkey(key)
    cert.sign(key, "sha256")

    # 将私钥和证书保存到文件
    with open(path + "server.key", "wb") as key_file:
        key_file.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, key))

    with open(path + "server.crt", "wb") as cert_file:
        cert_file.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))

    # 保存公钥
    with open(path + "server.pem", "wb") as pem_file:
        pem_file.write(crypto.dump_publickey(crypto.FILETYPE_PEM, key))

    return True
