import json
import os
import zipfile
import yaml
from pathlib import Path
from typing import Dict, Any, Type, TypeVar, get_origin, get_args


T = TypeVar("T", bound="BaseConfig")


class ConfigError(Exception):
    """配置相关异常基类"""


class ConfigTypeError(ConfigError):
    """配置类型错误"""


class ConfigValidationError(ConfigError):
    """配置验证失败"""


class BaseConfigMeta(type):
    """元类用于收集配置字段信息"""

    def __new__(cls, name, bases, namespace):
        # 处理配置路径继承
        if "__config_path__" not in namespace:  # 如果子类没有定义
            parent_config_path = (
                getattr(bases[0], "__config_path__", "config.yml")
                if bases
                else "config.yml"
            )
            namespace["__config_path__"] = parent_config_path

        # 收集类型注解和默认值
        annotations = namespace.get("__annotations__", {})
        fields = {}

        for attr_name, attr_value in namespace.items():
            if attr_name.startswith("_") or not isinstance(attr_value, Field):
                continue

            # 从Field对象中提取信息
            field_info = {
                "type": annotations.get(attr_name, type(attr_value.default)),
                "default": attr_value.default,
                "description": attr_value.description,
            }
            fields[attr_name] = field_info

        # 创建类并保存字段信息
        new_cls = super().__new__(cls, name, bases, namespace)
        new_cls.__fields__ = fields
        return new_cls


class Field:
    """配置字段描述符"""

    def __init__(self, default: Any, description: str = ""):
        self.default = default
        self.description = description


class BaseConfig(metaclass=BaseConfigMeta):
    __config_path__: str = "config.yml"  # 类级默认路径

    def __init__(self, config_path: str = None, **kwargs):
        # 初始化配置路径（支持实例级覆盖）
        self.__config_path__ = config_path or self.__class__.__config_path__

        # 初始化字段值
        for name, field in self.__fields__.items():
            value = kwargs.get(name, field["default"])
            setattr(self, name, value)

    @classmethod
    def load(cls: Type[T], config_path: str = None) -> T:
        """从YAML加载配置，若缺少字段则自动补全并写回文件"""
        target_path = config_path or cls.__config_path__
        config_path = Path(target_path)

        # 文件不存在，直接新建
        if not config_path.exists():
            instance = cls(config_path=target_path)
            instance.save()
            return instance

        # 读取已有配置
        with open(config_path, "r", encoding="utf-8") as f:
            raw_data = yaml.safe_load(f) or {}

        # 验证并填充默认值
        validated = cls._validate_config(raw_data)
        instance = cls(config_path=target_path, **validated)

        # 检查哪些字段在文件里缺失
        missing = [name for name in cls.__fields__ if name not in raw_data]
        if missing:
            # 可选：打印日志或提示
            print(f"[Config] 自动补全缺失字段：{missing}")
            # 把带注释的完整配置写回文件
            instance.save()

        return instance

    def save(self, config_path: str = None):
        """保存为带注释的YAML"""
        target_path = config_path or self.__config_path__
        config_path = Path(target_path)
        config_path.parent.mkdir(parents=True, exist_ok=True)

        yaml_data = self._generate_yaml_with_comments()

        with open(config_path, "w", encoding="utf-8") as f:
            f.write(yaml_data)

    def _generate_yaml_with_comments(self) -> str:
        """生成带注释的YAML内容"""
        lines = []
        for name, field in self.__fields__.items():
            # 添加注释
            comment = field["description"].replace("\n", "\n# ")
            lines.append(f"# {comment}")

            # 添加字段值
            value = getattr(self, name)
            yaml_line = yaml.dump(
                {name: value}, default_flow_style=False, allow_unicode=True
            ).strip()
            lines.append(yaml_line)

        return "\n".join(lines)

    @classmethod
    def _validate_config(cls, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """验证并处理配置数据"""
        validated = {}

        for name, field_info in cls.__fields__.items():
            # 获取用户设置的值或使用默认值
            value = raw_data.get(name, field_info["default"])

            # 类型验证
            if not cls._check_type(value, field_info["type"]):
                raise ConfigTypeError(
                    f"字段 '{name}' 类型错误，应为 {field_info['type']}，实际为 {type(value)}"
                )

            validated[name] = value

        return validated

    @staticmethod
    def _check_type(value: Any, expected_type: Type) -> bool:
        """类型检查"""
        # 处理泛型类型（如Dict, List等）
        origin = get_origin(expected_type)
        if origin is None:
            return isinstance(value, expected_type)

        # 处理Dict类型
        if origin is dict:
            args = get_args(expected_type)
            key_type, value_type = args[0], args[1]
            return (
                isinstance(value, dict)
                and all(isinstance(k, key_type) for k in value.keys())
                and all(isinstance(v, value_type) for v in value.values())
            )

        # 可以在此添加其他泛型类型的处理
        return isinstance(value, origin)

    def __setattr__(self, name, value):
        """属性设置时的类型检查"""
        if name in self.__fields__:
            field_type = self.__fields__[name]["type"]
            if not self._check_type(value, field_type):
                raise ConfigTypeError(
                    f"字段 '{name}' 类型错误，应为 {field_type}，实际为 {type(value)}"
                )
        super().__setattr__(name, value)

    def update(self, **kwargs):
        """批量更新配置"""
        for name, value in kwargs.items():
            if name not in self.__fields__:
                raise ConfigError(f"无效配置项: {name}")
            setattr(self, name, value)

    def print_config(self):
        """打印当前配置"""
        print("当前配置：")
        for name, field_info in self.__fields__.items():
            print(f"{name} ({field_info['type'].__name__}):")
            print(f"  值: {getattr(self, name)}")
            if field_info["description"]:
                print(f"  描述: {field_info['description']}")
            print()


class JsonDataEditor:
    def __init__(self, filepath="config.json"):
        self.filepath = filepath
        # 检查文件是否存在，如果不存在则创建空的JSON文件
        if not os.path.exists(filepath):
            path, _ = os.path.split(filepath)
            if path != "." and path:
                os.makedirs(
                    path, exist_ok=True
                )  # 使用 exist_ok=True 避免 FileExistsError
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
    def __init__(self, path: str, lang="en_us"):
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
