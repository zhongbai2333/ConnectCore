from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Tuple, TYPE_CHECKING

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import NestedCompleter
from prompt_toolkit.patch_stdout import patch_stdout

from connect_core.tools.tools import new_thread
from connect_core.cli.arguments import (
    ArgumentFactory,
    ArgumentSpec,
    ArgumentType,
    CommandSyntaxError,
    GreedyTextArgument,
    IntegerArgument,
    TextArgument,
)

if TYPE_CHECKING:  # pragma: no cover
    from connect_core.interface.control_interface import CoreControlInterface


CompleterTemplate = Dict[str, object]
_PLACEHOLDER_PATTERN = re.compile(r"<([^<>]+)>")


@dataclass
class CommandBinding:
    callback: Callable[..., None]
    placeholder_names: List[str]
    argument_specs: List[ArgumentSpec]
    pass_context: bool
    legacy: bool = False

    def __post_init__(self) -> None:
        if not self.legacy and len(self.argument_specs) != len(self.placeholder_names):
            raise ValueError(
                "参数定义数量与占位符不匹配: " + ", ".join(self.placeholder_names)
            )

    def build_arguments(
        self, params: List[str]
    ) -> Tuple[List[object], Dict[str, object]]:
        if self.legacy or not self.argument_specs:
            return list(params), {}

        values: List[object] = []
        context: Dict[str, object] = {}
        index = 0

        for spec in self.argument_specs:
            value, index = spec.parse(params, index)
            values.append(value)
            context[spec.name] = value

        if index < len(params):
            extra = " ".join(params[index:])
            raise CommandSyntaxError(f"存在多余参数: {extra}")

        return values, context if self.pass_context else {}


class CommandLineInterface:
    """轻量命令行调度器，支持嵌套命令与动态补全。"""

    def __init__(self, interface: "CoreControlInterface", prompt: str = ">>> ") -> None:
        self.prompt = prompt
        self.completer: Dict[str, CompleterTemplate] = {}
        self.commands: Dict[str, Dict[str, object]] = {}
        self._completer_templates: Dict[str, CompleterTemplate] = {}
        self._dynamic_lists: Dict[str, Callable[[], Iterable[str]]] = {}
        self.session: PromptSession[str] = PromptSession(
            completer=NestedCompleter.from_nested_dict(self.completer)
        )
        self.running = True
        self.interface = interface

    def set_prompt(self, prompt: str) -> None:
        self.prompt = prompt

    def register_dynamic_list(
        self, placeholder: str, resolver: Callable[[], Iterable[str]]
    ) -> None:
        key = placeholder.strip("[]")
        self._dynamic_lists[key] = resolver

    def set_completer_words(self, sid: str, words: CompleterTemplate) -> None:
        self._completer_templates[sid] = deepcopy(words)
        self.completer[sid] = self._expand_template(words)  # type: ignore[assignment]

    def add_command(
        self,
        sid: str,
        command: str,
        action: Callable[..., None],
        *,
        argument_specs: Optional[List[ArgumentSpec]] = None,
        pass_context: bool = False,
    ) -> None:
        segments = command.split()
        if not segments:
            return

        placeholder_names: List[str] = []
        node: dict[str, object] = self.commands.setdefault(sid, {})  # type: ignore[assignment]
        for segment in segments[:-1]:
            if self._is_placeholder(segment):
                placeholder_names.append(self._strip_placeholder(segment))
            node = node.setdefault(segment, {})  # type: ignore[assignment]

        last_segment = segments[-1]
        if self._is_placeholder(last_segment):
            placeholder_names.append(self._strip_placeholder(last_segment))

        if argument_specs:
            defined_names = [spec.name for spec in argument_specs]
            if defined_names != placeholder_names:
                raise ValueError(
                    f"命令 '{command}' 的参数定义顺序不匹配: {defined_names} vs {placeholder_names}"
                )

        specs = argument_specs or []
        binding = CommandBinding(
            callback=action,
            placeholder_names=placeholder_names,
            argument_specs=specs,
            pass_context=pass_context,
            legacy=argument_specs is None,
        )
        node[last_segment] = binding

    def remove_command(self, sid: str, command: str) -> None:
        if sid not in self.commands:
            return

        segments = command.split()
        if not segments:
            return

        stack = [self.commands[sid]]
        for segment in segments[:-1]:
            current = stack[-1]
            next_node = current.get(segment)
            if not isinstance(next_node, dict):
                return
            stack.append(next_node)

        stack[-1].pop(segments[-1], None)

        for depth in range(len(stack) - 1, 0, -1):
            parent = stack[depth - 1]
            key = segments[depth - 1]
            child = parent.get(key)
            if isinstance(child, dict) and not child:
                parent.pop(key, None)

    def remove_sid(self, sid: str) -> None:
        self.commands.pop(sid, None)
        self.completer.pop(sid, None)
        self._completer_templates.pop(sid, None)

    def flush_cli(self) -> None:
        for sid, template in self._completer_templates.items():
            self.completer[sid] = self._expand_template(template)  # type: ignore[assignment]
        self.session.app.current_buffer.completer = NestedCompleter.from_nested_dict(
            self.completer
        )
        self.session.app.invalidate()

    def _expand_template(self, template: object) -> object:
        if not isinstance(template, dict):
            return template

        expanded: Dict[str, object] = {}
        for key, value in template.items():
            if isinstance(key, str) and key.startswith("[") and key.endswith("]"):
                placeholder = key.strip("[]")
                resolver = self._dynamic_lists.get(placeholder)
                try:
                    generated = list(resolver()) if resolver else []
                except Exception as exc:  # pragma: no cover - defensive log
                    self.interface.logger.debug(
                        f"Failed to resolve completer placeholder '{placeholder}': {exc}"
                    )
                    generated = []

                for item in generated:
                    expanded[str(item)] = self._expand_template(deepcopy(value))
            else:
                expanded[key] = self._expand_template(value)
        return expanded

    def _resolve_command_path(
        self, command_tree: Dict[str, object], params: Iterable[str]
    ) -> Tuple[Optional[CommandBinding], List[str]]:
        node: object = command_tree
        captured: List[str] = []
        tokens = list(params)

        for index, token in enumerate(tokens):
            if isinstance(node, CommandBinding):
                captured.extend(tokens[index:])
                return node, captured

            if not isinstance(node, dict):
                break

            if token in node:
                node = node[token]
                continue

            placeholder_key = self._match_placeholder(node)
            if placeholder_key is None:
                command_text = " ".join(tokens[: index + 1])
                self.interface.logger.warning(
                    self.interface.translate(
                        "cli.command_core.unknown_command", command_text
                    )
                )
                return None, []

            captured.append(token)
            node = node[placeholder_key]

        if isinstance(node, dict):
            placeholder_key = self._match_placeholder(node)
            if placeholder_key is not None:
                name = self._strip_placeholder(placeholder_key)
                self.interface.logger.warning(f"缺少参数 <{name}>")
                return None, []
            return None, []

        if isinstance(node, CommandBinding):
            return node, captured

        return None, []

    @staticmethod
    def _match_placeholder(command_dict: Dict[str, object]) -> Optional[str]:
        for key in command_dict.keys():
            if isinstance(key, str) and key.startswith("<") and key.endswith(">"):
                return key
        return None

    @staticmethod
    def _is_placeholder(segment: str) -> bool:
        return segment.startswith("<") and segment.endswith(">")

    @staticmethod
    def _strip_placeholder(segment: str) -> str:
        return segment.strip("<>")

    def input_loop(self) -> None:
        while self.running:
            try:
                with patch_stdout():
                    text = self.session.prompt(
                        self.prompt,
                        completer=NestedCompleter.from_nested_dict(self.completer),
                    )
                    self.handle_input(text)
            except (KeyboardInterrupt, EOFError):
                self._handle_exit()

    def handle_input(self, text: str) -> None:
        if not text:
            return

        normalized = text.strip().lower()
        if normalized in {"exit", "quit"}:
            self._handle_exit()
            return

        parts = text.split()
        if not parts:
            return

        sid, *params = parts

        if sid not in self.commands:
            self.interface.logger.warning(
                self.interface.translate("cli.command_core.unknown_plugin", sid)
            )
            return

        if not params:
            params = ["help"]

        command, captured = self._resolve_command_path(self.commands[sid], params)
        if command is None:
            return

        if command.legacy:
            command.callback(*captured)
            return

        try:
            args, context = command.build_arguments(captured)
        except CommandSyntaxError as exc:
            self.interface.logger.warning(str(exc))
            return

        if context:
            command.callback(*args, context=context)
        else:
            command.callback(*args)

    @new_thread("CommandCore")
    def start(self) -> None:
        self.input_loop()

    def _handle_exit(self) -> None:
        if not self.running:
            return
        self.running = False
        self.interface.logger.info(self.interface.translate("cli.command_core.exiting"))
        try:
            self.session.app.exit()
        except Exception:  # pragma: no cover - best effort
            pass


class SimpleCommandBuilder:
    """简易命令构建器，提供声明式命令注册接口。"""

    def __init__(self) -> None:
        self._commands: List[Tuple[str, Callable[..., None], bool]] = []
        self._argument_factories: Dict[str, ArgumentFactory] = {}

    def command(
        self,
        definition: str,
        handler: Callable[..., None],
        *,
        pass_context: bool = False,
    ) -> "SimpleCommandBuilder":
        definition = definition.strip()
        if not definition:
            raise ValueError("命令定义不能为空")
        self._commands.append((definition, handler, pass_context))
        return self

    def arg(self, name: str, argument: ArgumentFactory) -> "SimpleCommandBuilder":
        name = name.strip()
        if not name:
            raise ValueError("参数名称不能为空")
        self._argument_factories[name] = argument
        return self

    def register(self, command_control: "CoreControlInterface.CommandControl") -> None:
        for definition, handler, pass_context in self._commands:
            placeholders = _PLACEHOLDER_PATTERN.findall(definition)
            specs: List[ArgumentSpec] = []
            for placeholder in placeholders:
                parser = self._create_argument_parser(placeholder)
                specs.append(ArgumentSpec(placeholder, parser))

            command_control.add_command(
                definition,
                handler,
                argument_specs=specs if specs else None,
                pass_context=pass_context,
            )

    def _create_argument_parser(self, name: str) -> ArgumentType:
        factory = self._argument_factories.get(name)
        if factory is None:
            return TextArgument()

        if isinstance(factory, ArgumentType):
            return deepcopy(factory)

        if isinstance(factory, type) and issubclass(factory, ArgumentType):
            return factory()

        if callable(factory):
            parser = factory()
            if not isinstance(parser, ArgumentType):
                raise TypeError(f"参数工厂返回了不是 ArgumentType 的对象: {name}")
            return parser

        raise TypeError(f"无法解析参数工厂: {name}")


__all__ = [
    "CommandLineInterface",
    "CommandBinding",
    "SimpleCommandBuilder",
]
