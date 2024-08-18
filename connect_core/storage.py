import json, os, zipfile
import yaml


class JsonDataEditor:
    def __init__(self, filepath="config.json"):
        self.filepath = filepath
        # 检查文件是否存在，如果不存在则创建空的JSON文件
        if not os.path.exists(filepath):
            self._write_data()

    def _read_data(self):
        """读取 JSON 文件内容并返回一个字典"""
        with open(self.filepath, "r", encoding="utf-8") as file:
            return json.load(file)

    def _write_data(self, data={}):
        """将字典写入 JSON 文件"""
        with open(self.filepath, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=4)

    def read(self):
        """获取当前 JSON 文件中的数据"""
        return self._read_data()

    def write(self, config):
        """向 JSON 文件中添加新的数据项"""
        global global_data_json
        self._write_data(config)


class YmlLanguage:

    def __init__(self, path: str, lang = "en_us"):
        self.full_path = path
        self.path, self.filename = os.path.split(path)
        self.translate = self._read_yaml(lang)

    # 读取yaml
    def _read_yaml(self, lang="en_us"):
        if zipfile.is_zipfile(self.full_path):
            with zipfile.ZipFile(self.full_path, "r") as pyz:
                with pyz.open(f"lang/{lang}.yml") as f:
                    config_data = f.read().decode("utf-8")
                    return yaml.safe_load(config_data)
        else:
            with open(f"{self.path}/lang/{lang}.yml", "r", encoding="utf-8") as f:
                data = yaml.load(stream=f, Loader=yaml.FullLoader)
                return data
