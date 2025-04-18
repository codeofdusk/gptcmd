"""
This module contains components of Gptcmd's macro support.
Copyright 2025 Bill Dengler
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""

import collections
from contextlib import contextmanager
import shlex
from string import Formatter
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    Sequence,
    TYPE_CHECKING,
    Union,
    Set,
)
import textwrap

if TYPE_CHECKING:
    from .cli import Gptcmd


class MacroError(Exception):
    def __init__(self, msg, line_num: Optional[int] = None):
        super().__init__(msg)
        self.line_num = line_num


class _MacroFormatter(Formatter):
    def get_value(
        self,
        key: Union[int, str],
        args: Sequence[Any],
        kwargs: Mapping[str, Any],
    ) -> Any:
        if key == "*":
            return shlex.join(args)
        elif isinstance(key, str) and key.isdecimal():
            key = int(key)
        if isinstance(key, int):
            if key <= 0:
                raise MacroError("Invalid argument index")
            idx = key - 1
            if idx >= len(args):
                raise MacroError(f"Missing positional argument {key}")
            return args[idx]
        else:
            try:
                return kwargs[key]
            except KeyError as e:
                raise MacroError(f"Undefined name {key!r}") from e

    def get_field(
        self, field_name: str, args: Sequence[Any], kwargs: Mapping[str, Any]
    ):
        if "." in field_name or "[" in field_name:
            raise MacroError(
                "Attribute and item access have not been implemented"
            )

        default = None
        if "?" in field_name:
            field_name, default = field_name.split("?", maxsplit=1)

        try:
            # This will call our overridden get_value, which might raise
            # a MacroError for missing positional arguments.
            obj, used_key = super().get_field(field_name, args, kwargs)
        except (KeyError, IndexError, MacroError):
            if default is None:
                raise
            obj, used_key = default, field_name

        return obj, used_key

    def check_unused_args(self, used_args, args, kwargs):
        pass


class _MacroEnvironment(collections.ChainMap):
    def __init__(self, shell: "Gptcmd"):
        super().__init__({}, _MacroBuiltins(shell))


class _MacroBuiltins(collections.abc.Mapping):
    _BUILTINS = {
        "thread": lambda sh: (
            sh._current_thread.name
            if sh._current_thread != sh._detached
            else ""
        ),
        "model": lambda sh: sh._account.provider.model,
        "account": lambda sh: sh._account.name,
    }

    def __init__(self, shell: "Gptcmd"):
        self._shell = shell

    def __getitem__(self, key: str):
        if key in self._BUILTINS:
            return str(self._BUILTINS[key](self._shell))
        raise KeyError(key)

    def __iter__(self):
        return iter(self._BUILTINS)

    def __len__(self):
        return len(self._BUILTINS)


class _MacroDirectiveHandler:
    _registry: Dict[str, Callable] = {}
    _PREFIX = "@"

    @classmethod
    def register(cls, name: str):
        def decorator(func):
            lower = name.lower()
            if lower in cls._registry:
                raise KeyError(f"Directive {name!r} already registered")
            cls._registry[lower] = func
            return func

        return decorator

    @classmethod
    def run(cls, spec: str, shell, env, line_num, macro_args):
        try:
            tokens = shlex.split(spec, posix=True)
        except ValueError as e:
            raise MacroError(f"Error parsing directive: {e}") from e

        if not tokens:
            raise MacroError("Empty directive specification")
        else:
            keyword, *args = tokens

        directive = cls._registry.get(keyword.lower())
        if directive is None:
            raise MacroError(f"Unknown directive {keyword!r}")

        directive(
            args,
            shell=shell,
            env=env,
            line_num=line_num,
            macro_args=macro_args,
        )


class MacroRunner:
    _STACK_DEPTH_LIMIT = 10

    def __init__(self, shell: "Gptcmd"):
        self._depth = 0
        self._formatter = _MacroFormatter()
        self._shell = shell
        self._active_macros: Set[str] = set()

    @contextmanager
    def _stack_frame(self):
        if self._depth >= self.__class__._STACK_DEPTH_LIMIT:
            raise MacroError("Stack overflow")
        self._depth += 1
        try:
            yield
        finally:
            self._depth -= 1

    def run(
        self,
        name: str,
        definition: str,
        args: Sequence[str],
    ) -> bool:
        # The active_macros set tracks macros currently on the execution stack
        # to prevent recursion. A macro is added when it starts and removed
        # when it finishes, so calling the same macro sequentially is fine.
        if name in self._active_macros:
            raise MacroError(f"Recursive invocation of macro {name!r}")
        self._active_macros.add(name)
        try:
            with self._stack_frame():
                env = _MacroEnvironment(self._shell)
                for line_num, tpl in enumerate(
                    self.__class__._split(definition), start=1
                ):
                    try:
                        if tpl.startswith(_MacroDirectiveHandler._PREFIX):
                            _MacroDirectiveHandler.run(
                                tpl[1:].lstrip(),
                                shell=self._shell,
                                env=env,
                                line_num=line_num,
                                macro_args=args,
                            )
                        else:
                            try:
                                rendered = self._formatter.vformat(
                                    tpl, args, env
                                )
                            except ValueError as e:
                                raise MacroError(
                                    f"Invalid format string: {e}"
                                ) from e
                            if self._shell.onecmd(rendered):
                                return True
                    except MacroError as e:
                        if e.line_num is None:
                            e.line_num = line_num
                        raise
        finally:
            self._active_macros.discard(name)
        return False

    @staticmethod
    def _split(definition: str) -> List[str]:
        dedented = textwrap.dedent(definition)
        return [
            raw.strip()
            for raw in dedented.splitlines()
            if raw.strip() and not raw.lstrip().startswith("#")
        ]
