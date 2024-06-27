from cryptography.fernet import Fernet, InvalidToken
from connect_core.get_config_translate import config, translate
from connect_core.log_system import error_print, debug_print

global fernet

def rsa_main():
    global fernet

    if config("password"):
        fernet = Fernet(config("password").encode())
    else:
        fernet = None


# 加密
def rsa_encrypt(data: bytes):
    if fernet:
        return fernet.encrypt(data)
    else:
        raise InvalidToken("Passowrd init Error!")


# 解密
def rsa_decrypt(data: bytes):
    if fernet and data:
        try:
            return fernet.decrypt(data)
        except InvalidToken as e:
            error_print(translate("rsa.decrypt_error"))
            raise InvalidToken(e)
    else:
        raise InvalidToken("Passowrd init Error or data error!")
