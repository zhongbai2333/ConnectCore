from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Tuple, Union


class CommandSyntaxError(Exception):
    """命令参数解析错误。"""


class ArgumentType:
    greedy: bool = False

    def parse(self, tokens: List[str], index: int, name: str) -> Tuple[object, int]:
        raise NotImplementedError


class TextArgument(ArgumentType):
    def parse(self, tokens: List[str], index: int, name: str) -> Tuple[str, int]:
        if index >= len(tokens):
            raise CommandSyntaxError(f"缺少参数 <{name}>")
        return tokens[index], index + 1


class IntegerArgument(ArgumentType):
    def parse(self, tokens: List[str], index: int, name: str) -> Tuple[int, int]:
        if index >= len(tokens):
            raise CommandSyntaxError(f"缺少参数 <{name}>")
        raw = tokens[index]
        try:
            value = int(raw)
        except ValueError as exc:
            raise CommandSyntaxError(f"参数 <{name}> 不是整数: {raw}") from exc
        return value, index + 1


class GreedyTextArgument(ArgumentType):
    greedy = True

    def parse(self, tokens: List[str], index: int, name: str) -> Tuple[str, int]:
        if index >= len(tokens):
            raise CommandSyntaxError(f"缺少参数 <{name}>")
        return " ".join(tokens[index:]), len(tokens)


@dataclass
class ArgumentSpec:
    name: str
    parser: ArgumentType

    def parse(self, tokens: List[str], index: int) -> Tuple[object, int]:
        return self.parser.parse(tokens, index, self.name)


ArgumentFactory = Union[ArgumentType, type[ArgumentType], Callable[[], ArgumentType]]
