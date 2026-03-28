import yaml  # type: ignore[import-untyped]
from pathlib import Path
from typing import Any, Dict, Type, TypeVar, get_origin, get_args, Union
from os import PathLike

from pydantic import BaseModel, ConfigDict, ValidationError
from pydantic import Field as PydanticField
from pydantic.fields import FieldInfo

T = TypeVar("T", bound="BaseConfig")


class ConfigError(Exception):
    """配置相关异常基类"""


class ConfigTypeError(ConfigError):
    """配置类型错误"""


class ConfigValidationError(ConfigError):
    """配置验证失败"""


def Field(default: Any = ..., description: str = "") -> Any:
    """向后兼容的 Field 工厂，委托给 pydantic.Field。"""
    return PydanticField(default=default, description=description)


class BaseConfig(BaseModel):
    """基于 pydantic 的 YAML 配置基类。"""

    model_config = ConfigDict(validate_assignment=True)

    __config_path__: str = "config.yml"

    # ------------------------------------------------------------------
    # 向后兼容: __fields__ 属性
    # 旧代码通过 cls.__fields__ / instance.__fields__ 获取字段信息字典。
    # pydantic v2 使用 model_fields，这里提供兼容桥接。
    # ------------------------------------------------------------------
    @classmethod
    def _compat_fields(cls) -> Dict[str, Dict[str, Any]]:
        result: Dict[str, Dict[str, Any]] = {}
        for name, fi in cls.model_fields.items():
            result[name] = {
                "type": fi.annotation,
                "default": fi.default,
                "description": fi.description or "",
            }
        return result

    # 使类和实例都能通过 .__fields__ 访问兼容字典
    class __fields__descriptor__:
        """Descriptor that works on both class and instance access."""

        def __get__(
            self, obj: Any, objtype: type | None = None
        ) -> Dict[str, Dict[str, Any]]:
            cls = objtype if objtype is not None else type(obj)
            return cls._compat_fields()  # type: ignore[attr-defined, no-any-return]

    __fields__: Any = __fields__descriptor__()  # type: ignore[assignment]

    def __init__(
        self, config_path: str | PathLike[str] | None = None, **kwargs: Any
    ) -> None:
        try:
            super().__init__(**kwargs)
        except ValidationError as exc:
            raise ConfigTypeError(str(exc)) from exc
        # 使用 object.__setattr__ 避免 pydantic 验证 (非模型字段)
        object.__setattr__(
            self, "__config_path__", config_path or self.__class__.__config_path__
        )

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # 继承 __config_path__
        if "__config_path__" not in cls.__dict__:
            for base in cls.__mro__[1:]:
                if "__config_path__" in base.__dict__:
                    cls.__config_path__ = base.__dict__["__config_path__"]
                    break

    # ---- 验证赋值时抛出 ConfigTypeError 而不是 pydantic ValidationError ----
    def __setattr__(self, name: str, value: Any) -> None:
        if name in self.model_fields:
            try:
                super().__setattr__(name, value)
            except Exception as exc:
                raise ConfigTypeError(
                    f"字段 '{name}' 类型错误，应为 {self.model_fields[name].annotation}，"
                    f"实际为 {type(value)}"
                ) from exc
        else:
            object.__setattr__(self, name, value)

    # ------------------------------------------------------------------
    # load / save — 保留原有 YAML 行为
    # ------------------------------------------------------------------
    @classmethod
    def load(cls: Type[T], config_path: str | PathLike[str] | None = None) -> T:
        """从YAML加载配置，若缺少字段则自动补全并写回文件"""
        target_path = config_path or cls.__config_path__
        file_path = Path(target_path)

        if not file_path.exists():
            instance = cls(config_path=target_path)
            instance.save()
            return instance

        with open(file_path, "r", encoding="utf-8") as f:
            raw_data = yaml.safe_load(f) or {}

        validated = cls._validate_config(raw_data)
        instance = cls(config_path=target_path, **validated)

        missing = [name for name in cls.model_fields if name not in raw_data]
        if missing:
            print(f"[Config] 自动补全缺失字段：{missing}")
            instance.save()

        return instance

    def save(self, config_path: str | PathLike[str] | None = None) -> None:
        """保存为带注释的YAML"""
        target_path = config_path or self.__config_path__
        file_path = Path(target_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        yaml_data = self._generate_yaml_with_comments()
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(yaml_data)

    def _generate_yaml_with_comments(self) -> str:
        """生成带注释的YAML内容"""
        lines: list[str] = []
        for name, fi in self.model_fields.items():
            comment = (fi.description or "").replace("\n", "\n# ")
            lines.append(f"# {comment}")
            value = getattr(self, name)
            yaml_line = yaml.dump(
                {name: value}, default_flow_style=False, allow_unicode=True
            ).strip()
            lines.append(yaml_line)
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # _validate_config — 兼容旧调用，同时利用 pydantic 验证
    # ------------------------------------------------------------------
    @classmethod
    def _validate_config(cls, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """验证并处理配置数据"""
        validated: Dict[str, Any] = {}
        for name, fi in cls.model_fields.items():
            value = raw_data.get(name, fi.default)
            if not cls._check_type(value, fi.annotation):
                raise ConfigTypeError(
                    f"字段 '{name}' 类型错误，应为 {fi.annotation}，实际为 {type(value)}"
                )
            validated[name] = value
        return validated

    @staticmethod
    def _check_type(value: Any, expected_type: Any) -> bool:
        """增强的类型检查器，支持泛型类型"""
        origin = get_origin(expected_type)
        args = get_args(expected_type)

        if origin is None:
            return isinstance(value, expected_type)

        if origin is Union:
            return any(BaseConfig._check_type(value, arg) for arg in args)

        if origin is list:
            if not isinstance(value, list):
                return False
            item_type = args[0]
            return all(BaseConfig._check_type(item, item_type) for item in value)

        if origin is dict:
            if not isinstance(value, dict):
                return False
            key_type, val_type = args
            return all(
                BaseConfig._check_type(k, key_type)
                and BaseConfig._check_type(v, val_type)
                for k, v in value.items()
            )

        return isinstance(value, origin)

    def update(self, **kwargs: Any) -> None:
        """批量更新配置"""
        for name, value in kwargs.items():
            if name not in self.model_fields:
                raise ConfigError(f"无效配置项: {name}")
            setattr(self, name, value)
