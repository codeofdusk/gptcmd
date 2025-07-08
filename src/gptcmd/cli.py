"""
This module contains the Gptcmd class and serves as an entry point to the
Gptcmd command line application.
Copyright 2024 Bill Dengler
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""

import argparse
import atexit
import cmd
import concurrent.futures
import dataclasses
import datetime
import difflib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import traceback
from ast import literal_eval
from textwrap import shorten
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Sequence,
    Tuple,
    Type,
)

from .config import ConfigError, ConfigManager
from .llm import CompletionError, InvalidAPIParameterError, LLMProviderFeature
from .macros import MacroError, MacroRunner
from .message import (
    Audio,
    Image,
    Message,
    MessageAttachment,
    MessageRole,
    MessageThread,
    PopStickyMessageError,
)

__version__ = "2.2.0"


def input_with_handling(_input: Callable) -> Callable:
    "Catch KeyboardInterrupt to avoid crashing"

    def _inner(*args):
        try:
            return _input(*args)
        except KeyboardInterrupt:
            print("")
            return "\n"

    return _inner


class Gptcmd(cmd.Cmd):
    "Represents the Gptcmd command line application"

    intro = (
        f"Welcome to Gptcmd {__version__}! Type help or ? to list commands.\n"
    )

    def __init__(
        self,
        thread_cls=MessageThread,
        config: Optional[ConfigManager] = None,
        *args,
        **kwargs,
    ):
        self.thread_cls = thread_cls
        self.last_path = None
        self.config = config or ConfigManager.from_toml()
        self._check_macro_names()
        self._account = self.config.default_account
        self._detached = self.thread_cls("*detached*")
        self._current_thread = self._detached
        self._threads = {}
        self._session_cost_in_cents = 0
        self._session_cost_incomplete = False
        self._future_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1
        )
        self._macro_runner = MacroRunner(self)
        super().__init__(*args, **kwargs)

    @property
    def prompt(self):
        threadname = (
            ""
            if self._current_thread == self._detached
            else self._current_thread.name
        )
        return self.config.conf["prompt"].format(
            thread=threadname,
            model=self._account.provider.model,
            account=self._account.name,
        )

    @staticmethod
    def _fragment(tpl: str, msg: Message) -> str:
        """
        Returns an output string containing part of a message to provide
        context for certain operations. The tpl parameter contains a string in
        which this message fragment should be displayed. The characters {msg}
        are replaced with the message fragment.
        """
        PLACEHOLDER = "..."
        MAX_LENGTH = 79
        MIN_LENGTH = 5
        # length of the template once the fragment is stripped out
        head_length = len(tpl.replace("{msg}", ""))
        # 2 extra chars because repr() will add surrounding quotes
        avail = max(MIN_LENGTH, MAX_LENGTH - head_length - 2)

        short = shorten(msg.content, avail, placeholder=PLACEHOLDER)

        if short == PLACEHOLDER:
            short = msg.content[:avail] + PLACEHOLDER

        return tpl.format(msg=repr(short))

    @staticmethod
    def _user_range_to_python_range(
        ref: str, allow_single: bool = True, strict_range: bool = True
    ) -> Tuple[Optional[int], Optional[int]]:
        tokens = ref.split()
        if not tokens:
            raise ValueError("No indices provided")
        if len(tokens) == 1:
            if tokens[0] == ".":
                return (None, None)
            if not allow_single:
                raise ValueError("Wrong number of indices")
            start = end = tokens[0]
        elif len(tokens) == 2:
            start, end = tokens
        else:
            raise ValueError("Wrong number of indices")

        def _convert(token: str, is_start: bool) -> Optional[int]:
            if token == ".":
                return None
            val = int(token)
            if is_start:
                return val - 1 if val > 0 else val
            else:
                if val > 0:
                    return val
                elif val == -1:
                    return None
                else:
                    return val + 1

        py_start = _convert(start, True)
        py_end = _convert(end, False)

        if len(tokens) == 1:
            if py_start == -1:
                py_end = None
            elif py_start is not None:
                py_end = py_start + 1
        if (
            strict_range
            and py_start is not None
            and py_end is not None
            and py_start >= py_end
        ):
            raise ValueError("Range end is beyond its start")
        return py_start, py_end

    @staticmethod
    def _confirm(prompt: str) -> bool:
        POSITIVE_STRINGS = ("y", "yes")
        NEGATIVE_STRINGS = ("n", "no")
        yn = None
        while yn not in (*POSITIVE_STRINGS, *NEGATIVE_STRINGS):
            yn = input(f"{prompt} (y/n)")
        return yn in POSITIVE_STRINGS

    @staticmethod
    def _complete_from_key(d: Dict, text: str) -> List[str]:
        return [k for k, v in d.items() if k.startswith(text)]

    @staticmethod
    def _lex_args(line: str) -> List[str]:
        "Lex a string into a list of shell-like arguments"
        lexer = shlex.shlex(line, posix=True)
        lexer.escape = ""
        lexer.whitespace_split = True
        return list(lexer)

    @staticmethod
    def _await_future_interruptible(
        future: concurrent.futures.Future, interval: float = 0.25
    ):
        """
        Block until the future finishes, waking up
        at the supplied interval so the main thread can raise
        interrupts immediately.
        Returns future.result().
        """
        while True:
            try:
                return future.result(timeout=interval)
            except concurrent.futures.TimeoutError:
                continue

    @staticmethod
    def _menu(prompt: str, options: List[str]) -> Optional[str]:
        """
        Display a menu of options and return the chosen item, or None
        if canceled.
        """
        while True:
            print(
                prompt,
                "0. Cancel",
                *(
                    f"{i}. {option}"
                    for i, option in enumerate(options, start=1)
                ),
                sep="\n",
            )
            selection = input("Enter your selection: ")
            if not selection.isdigit():
                continue
            choice = int(selection)
            if choice == 0:
                return None
            if 1 <= choice <= len(options):
                return options[choice - 1]

    @staticmethod
    def _json_eval(s: str) -> Any:
        """
        Evaluate a Python literal from a string, restricted to values
        encodable as JSON
        """
        PYTHON_TYPES = {
            "True": True,
            "False": False,
            "None": None,
        }
        if s in PYTHON_TYPES:
            return PYTHON_TYPES[s]
        return json.loads(s)

    KNOWN_ROLES = tuple(MessageRole)

    @classmethod
    def _complete_role(cls, text: str) -> List[str]:
        return [role for role in cls.KNOWN_ROLES if role.startswith(text)]

    @classmethod
    def _validate_role(cls, role: str) -> bool:
        return role in cls.KNOWN_ROLES

    @classmethod
    def _disambiguate(
        cls, user_input: str, choices: Sequence[str]
    ) -> Optional[str]:
        DIFFLIB_CUTOFF = 0.5
        MAX_MATCHES = 9

        in_lower = user_input.lower()
        matches = difflib.get_close_matches(
            user_input,
            choices,
            n=MAX_MATCHES,
            cutoff=DIFFLIB_CUTOFF,
        )

        if len(user_input) > 2:
            matches.extend(
                [
                    c
                    for c in choices
                    if in_lower in c.lower() and c not in matches
                ]
            )

        if not matches:
            return None

        ratio = {
            c: difflib.SequenceMatcher(None, user_input, c).ratio()
            for c in matches
        }

        def _has_non_digit_suffix(s: str) -> int:
            # 1 when the last hyphen/underscore-separated token is not
            # purely digits, 0 otherwise.
            last = re.split(r"[-_]", s)[-1]
            return int(not last.isdigit())

        def _max_numeric_token(s: str) -> int:
            # Greatest integer appearing anywhere in the candidate, or ‑1
            nums = re.findall(r"\d+", s)
            return max(map(int, nums)) if nums else -1

        matches = sorted(
            matches,
            key=lambda c: (
                # Literal match (prefer prefix)
                (
                    0
                    if c.lower().startswith(in_lower)
                    else 1 if in_lower in c.lower() else 2
                ),
                # Suffix match (prefer non-digit)
                # Heuristic: Prefer unversioned model aliases
                -_has_non_digit_suffix(c),
                # Difflib match (best first)
                -ratio[c],
                # Length match (shortest first)
                # Heuristic: Prefer unversioned model aliases
                len(c),
                # Numeric match (prefer larger numbers)
                # Heuristic: Prefer later model versions
                -_max_numeric_token(c),
                # Fallback: Lexicographic order
                c,
            ),
        )[:MAX_MATCHES]

        if len(matches) == 1:
            c = matches[0]
            match = c if cls._confirm(f"Did you mean {c!r}?") else None
        else:
            match = cls._menu("Did you mean one of these?", matches)
        if match is None:
            print("Cancelled")
        return match

    def _check_macro_names(self) -> None:
        """Raise if any macro name collides with a built-in command."""
        builtin_cmds = {
            attr[3:]  # strip leading 'do_'
            for attr in dir(self.__class__)
            if attr.startswith("do_")
            and callable(getattr(self.__class__, attr))
        }
        for overlap in builtin_cmds & self.config.macros.keys():
            raise ConfigError(f"Invalid macro name {overlap!r}")

    def emptyline(self):
        "Disable Python cmd's repeat last command behaviour."
        pass

    def default(self, line: str) -> bool:
        name, arg, _ = self.parseline(line)
        if name and name in self.config.macros:
            is_system_macro = name.startswith(
                self.config.SYSTEM_MACRO_PREFIX
            ) and name.endswith(self.config.SYSTEM_MACRO_SUFFIX)
            if not is_system_macro:
                try:
                    args = self.__class__._lex_args(arg)
                except ValueError as e:
                    print(f"Error parsing macro arguments: {e}")
                    return False
                return self._run_macro(name, args)
        return super().default(line)

    def cmdloop(self, *args, **kwargs):
        old_input = cmd.__builtins__["input"]
        cmd.__builtins__["input"] = input_with_handling(old_input)
        try:
            super().cmdloop(*args, **kwargs)
        finally:
            cmd.__builtins__["input"] = old_input

    def do_thread(self, arg, _print_on_success=True):
        """
        Switch to the thread passed as argument, creating it as a clone of the
        current thread if the supplied name does not exist. With no argument,
        switch to the detached thread.
        example: "thread messages" switches to the thread named "messages",
        creating it if necessary.
        """
        if not arg:
            self._current_thread = self._detached
            if _print_on_success:
                print("detached thread")
            return
        if arg not in self._threads:
            targetstr = "new thread"
            self._threads[arg] = self.thread_cls(
                name=arg,
                messages=self._current_thread.messages,
                names=self._current_thread.names,
            )
            if self._current_thread == self._detached and self._detached.dirty:
                self._detached.dirty = False
        else:
            targetstr = "thread"
        self._current_thread = self._threads[arg]
        if _print_on_success:
            print(f"Switched to {targetstr} {repr(self._current_thread.name)}")

    def complete_thread(self, text, line, begidx, endidx):
        return self.__class__._complete_from_key(self._threads, text)

    def do_threads(self, arg):
        """
        List all named threads in the current session. This command takes no
        arguments.
        """
        t = sorted(
            [(k, len(v)) for k, v in self._threads.items()],
            key=lambda x: x[1],
        )[::-1]
        if len(t) < 1:
            print("No threads")
        for name, count in t:
            if count == 1:
                msg = "message"
            else:
                msg = "messages"
            print(f"{name} ({count} {msg})")
        if self._detached:
            print(f"({len(self._detached)} detached messages)")

    def _should_allow_add_empty_messages(self, role: MessageRole) -> bool:
        allow_add_empty_messages = self.config.conf.get(
            "allow_add_empty_messages"
        )
        if allow_add_empty_messages == "always":
            return True
        elif allow_add_empty_messages == "ask":
            return self.__class__._confirm(f"Add empty {role} message?")
        else:  # never (default)
            return False

    def _append_new_message(
        self,
        arg: str,
        role: MessageRole,
        _print_on_success: bool = True,
        _edit_on_empty: bool = True,
    ) -> Optional[Message]:
        if not arg and _edit_on_empty:
            arg = self._edit_interactively("")
            if not arg:
                if self._should_allow_add_empty_messages(role):
                    arg = ""
                else:
                    print("Cancelled")
                    return None
        msg = Message(content=arg, role=role)
        actor = (
            f"{self._current_thread.names[role]!r} ({role})"
            if role in self._current_thread.names
            else role
        )
        self._current_thread.append(msg)
        if _print_on_success:
            print(self.__class__._fragment("{msg} added as " + actor, msg))
        return msg

    def _run_macro(self, name: str, args: List[str]) -> bool:
        definition = self.config.macros[name]
        try:
            return self._macro_runner.run(name, definition, args)
        except MacroError as e:
            line_info = (
                f", line {e.line_num}" if e.line_num is not None else ""
            )
            print(f"Error in macro {name!r}{line_info}: {e}")
        return False

    def do_user(self, arg):
        """
        Append a new user message (with content provided as argument) to the
        current thread. With no argument, opens an external editor for
        message composition.
        example: "user Hello, world!"
        """
        self._append_new_message(arg=arg, role=MessageRole.USER)

    def do_assistant(self, arg):
        """
        Append a new assistant message (with content provided as argument) to
        the current thread. With no argument, opens an external editor for
        message composition.
        example: "assistant how can I help?"
        """
        self._append_new_message(arg=arg, role=MessageRole.ASSISTANT)

    def do_system(self, arg):
        """
        Append a new system message (with content provided as argument) to the
        current thread. With no argument, opens an external editor for
        message composition.
        example: "system You are a friendly assistant."
        """
        self._append_new_message(arg=arg, role=MessageRole.SYSTEM)

    def do_first(self, arg):
        """
        Display the first n messages, or pass no arguments for the first
        message.
        example: "first 5"
        """
        if not arg:
            end_index = 1
        else:
            try:
                end_index = int(arg.strip())
            except ValueError:
                print("Usage: first <n> – shows the first n messages.")
                return
        print(self._current_thread.render(start_index=0, end_index=end_index))

    def do_last(self, arg):
        """
        Display the last n messages, or pass no arguments for the last message.
        example: "last 5"
        """
        if not arg:
            start_index = -1
        else:
            try:
                start_index = int(arg) * -1
            except ValueError:
                print("Usage: last <n> – shows the last n messages.")
                return
        print(self._current_thread.render(start_index=start_index))

    def do_view(self, arg):
        """
        Pass no arguments to read the entire thread in cronological order.
        Optionally, pass a range of messages to read that range.
        example: "view 1 4" views the first through fourth message.
        """
        if not arg:
            start = None
            end = None
        else:
            try:
                start, end = self.__class__._user_range_to_python_range(arg)
            except ValueError:
                print("Invalid view range")
                return
        print(self._current_thread.render(start_index=start, end_index=end))

    def do_send(self, arg):
        """
        Send the current thread to the language model and print the response.
        This command takes no arguments.
        """
        print("...")
        # Run the potentially long-running provider call in a background
        # thread so Ctrl+c can interrupt immediately.
        future = self._future_executor.submit(
            self._account.provider.complete, self._current_thread
        )

        try:
            res = self.__class__._await_future_interruptible(future)
        except KeyboardInterrupt:
            future.cancel()
            print("\nCancelled")
            # This API request may have incurred cost
            self._session_cost_incomplete = True
            return
        except (CompletionError, NotImplementedError, ValueError) as e:
            print(str(e))
            return

        try:
            for chunk in res:
                print(chunk, end="")
            print("\n", end="")
        except KeyboardInterrupt:
            print("\nDisconnected from stream")
        except CompletionError as e:
            print(str(e))
        finally:
            if res.message.role and res.message.content:
                self._current_thread.append(res.message)
            cost_info = ""
            if res.cost_in_cents is not None:
                self._session_cost_in_cents += res.cost_in_cents
                cost = round(self._session_cost_in_cents / 100, 2)
                prefix = (
                    "Incomplete estimate of session cost"
                    if self._session_cost_incomplete
                    else "Estimated session cost"
                )
                cost_info = f"{prefix}: ${cost:.2f}"
            else:
                self._session_cost_incomplete = True

            token_info = ""
            if res.prompt_tokens and res.sampled_tokens:
                token_info = (
                    f"{res.prompt_tokens} prompt, {res.sampled_tokens} sampled"
                    " tokens used for this request"
                )

            show_cost = (
                cost_info
                and self.config.conf["show_cost"]
                and (
                    not self._session_cost_incomplete
                    or self.config.conf["show_incomplete_cost"]
                )
            )
            show_token_usage = (
                token_info and self.config.conf["show_token_usage"]
            )

            if show_cost and show_token_usage:
                print(f"{cost_info} ({token_info})")
            elif show_token_usage:
                print(token_info)
            elif show_cost:
                print(cost_info)

    def do_say(self, arg):
        """
        Append a new user message (with content provided as argument) to the
        current thread, then send the thread to the language model and print
        the response.
        example: "say Hello!"
        """
        if self._append_new_message(
            arg, MessageRole.USER, _print_on_success=False
        ):
            self.do_send(None)

    def do_pop(self, arg):
        """
        Delete the ith message, or pass no argument to delete the last.
        example: "pop -2" deletes the penultimate message.
        """
        if not self._current_thread:
            print("No messages")
            return
        try:
            if arg:
                n = int(arg)
                if n > 0:
                    n -= 1
                msg = self._current_thread.pop(n)
            else:
                msg = self._current_thread.pop()
            print(self.__class__._fragment("{msg} deleted", msg))
        except IndexError:
            print("Message doesn't exist")
        except ValueError:
            print("Usage: pop <i> – deletes the ith message")
        except PopStickyMessageError:
            print("That message is sticky; unsticky it first")

    def do_clear(self, arg):
        """
        Delete all messages in the current thread. This command takes no
        arguments.
        """
        stickys = self._current_thread.stickys
        length = len(self._current_thread) - len(stickys)
        if length < 1:
            print("No messages")
            return
        mq = "message" if length == 1 else "messages"
        can_clear = self.__class__._confirm(f"Delete {length} {mq}?")
        if can_clear:
            self._current_thread.messages = stickys
            print("Cleared")

    def do_delete(self, arg):
        """
        Delete the named thread passed as argument. With no argument, deletes
        all named threads in this session.
        example: "delete messages" deletes the thread named "messages".
        """
        if not self._threads:
            print("No threads")
            return
        if not arg:
            length = len(self._threads)
            suffix = "thread" if length == 1 else "threads"
            can_delete = self.__class__._confirm(f"Delete {length} {suffix}?")
            if can_delete:
                self._threads = {}
                self._current_thread = self._detached
                print("Deleted")
        elif arg in self._threads:
            if self._threads[arg] == self._current_thread:
                self._current_thread = self._detached
            del self._threads[arg]
            print(f"Deleted thread {arg}")
        else:
            print(f"{arg} doesn't exist")

    def complete_delete(self, text, line, begidx, endidx):
        return self.__class__._complete_from_key(self._threads, text)

    def do_move(self, arg):
        """
        Move the message at the beginning of a range to the end of that range.
        In other words, move <i> <j> moves the ith message of a thread to
        index j.
        """
        if not arg:
            print("Usage: move <from> <to>")
            return
        try:
            i, j = self._user_range_to_python_range(
                arg, allow_single=False, strict_range=False
            )
        except ValueError:
            print("Invalid range specified")
            return
        length = len(self._current_thread.messages)
        if i is None:
            i = 0
        if j is None:
            j = length
        if i < 0:
            i += length
        if j < 0:
            j += length
        elif j > 0:
            j -= 1  # Adjust end for 1-based indexing
        if not (0 <= j <= length):
            print("Destination out of bounds")
            return
        try:
            msg = self._current_thread.move(i, j)
        except IndexError:
            print("Message doesn't exist")
            return
        except PopStickyMessageError:
            print("That message is sticky; unsticky it first")
            return
        if j == i:
            move_info = "to same position"
        elif j == 0:
            move_info = "to start"
        elif j >= length - 1:
            move_info = "to end"
        elif j > i:
            move_info = self._fragment(
                "before {msg}", msg=self._current_thread.messages[j + 1]
            )
        elif j < i:
            move_info = self._fragment(
                "after {msg}", msg=self._current_thread.messages[j - 1]
            )
        else:
            move_info = "to unknown position"
        print(self.__class__._fragment("{msg} moved ", msg=msg) + move_info)

    def do_copy(self, arg):
        """
        Append copies of the messages in the specified range to the thread
        provided. If no thread name is specified, the copy command copies
        messages to the detached thread.
        example: "copy 1 3" copies the first through third message of this
        thread to the detached thread.
        "copy . messages" copies all messages in this thread to a thread
        called "messages", creating it if it doesn't exist.
        """
        m = re.match(
            (r"((?:-?\d+|\.)(?:\s+-?\d+|\s*\.)*)" r"(?: (\S+))?$"), arg
        )
        if not m:
            print("Usage: copy <range> [thread]")
            return
        ref, threadname = m.groups()
        try:
            start, end = self.__class__._user_range_to_python_range(ref)
        except ValueError:
            print("Invalid range")
            return
        s = self._current_thread[start:end]
        if not s:
            print("Empty selection")
            return
        if len(s) == 1:
            print(
                self.__class__._fragment(
                    "Selection contains one message: {msg}", s[0]
                )
            )
        else:
            print(f"Selecting {len(s)} messages")
            print(
                self.__class__._fragment("First message selected: {msg}", s[0])
            )
            print(
                self.__class__._fragment("Last message selected: {msg}", s[-1])
            )
        if threadname is None:
            thread = self._detached
            thread_info = "detached thread"
        elif threadname in self._threads:
            thread = self._threads.get(threadname)
            thread_info = threadname
        else:
            thread = None
            thread_info = f"New thread {threadname}"
        can_copy = self.__class__._confirm(f"Copy to {thread_info}?")
        if not can_copy:
            return
        if thread is None:  # if this is a new thread
            self._threads[threadname] = self.thread_cls(
                name=threadname,
                messages=s,
                names=self._current_thread.names,
            )
        else:
            for msg in s:
                thread.append(dataclasses.replace(msg))
        print("Copied")

    def do_retry(self, arg):
        """
        Delete up to the last non-sticky assistant message, then send the
        conversation to the language model. This command takes no arguments.
        """
        if not any(
            m.role != MessageRole.ASSISTANT for m in self._current_thread
        ):
            print("Nothing to retry!")
            return
        if self._current_thread != self._detached:
            create_new_thread_on_retry = self.config.conf.get(
                "create_new_thread_on_retry", "always"
            )
            should_create = None
            is_numbered_thread = re.match(
                r"(.*?)(\d+$)", self._current_thread.name
            )
            if self._current_thread.name.isdigit():
                basename = self._current_thread.name
                num = 2
            elif is_numbered_thread:
                basename = is_numbered_thread.group(1)
                num = int(is_numbered_thread.group(2))
            else:
                basename = self._current_thread.name
                num = 2
            while basename + str(num) in self._threads:
                num += 1
            newname = basename + str(num)

            if create_new_thread_on_retry == "ask":
                should_create = self.__class__._confirm(
                    f"Create thread {newname!r}?"
                )
            elif create_new_thread_on_retry == "never":
                should_create = False
            else:
                should_create = True

            if should_create:
                self.do_thread(newname)
        for i in range(len(self._current_thread) - 1, -1, -1):
            role = self._current_thread[i].role
            if role == MessageRole.ASSISTANT:
                try:
                    self._current_thread.pop(i)
                    break
                except PopStickyMessageError:
                    continue
        self.do_send(None)

    def do_model(self, arg, _print_on_success=True):
        """
        Change the model used by the current thread. Pass no argument to
        check the currently active model.
        example: "model gpt-3.5-turbo"
        """
        if not arg:
            print(f"Current model: {self._account.provider.model}")
            return
        if self._account.provider.valid_models is None:
            is_valid_model = self.__class__._confirm(
                f"{self._account.name} does not support model validation. "
                "If this model does not exist, requests to it will fail. "
                "Switch anyway?"
            )
        else:
            is_valid_model = arg in self._account.provider.valid_models
        if is_valid_model:
            self._account.provider.model = arg
            if _print_on_success:
                print(f"Switched to model {self._account.provider.model!r}")
        else:
            print(f"{arg} is currently unavailable")
            valid_models = self._account.provider.valid_models or ()
            match = self.__class__._disambiguate(arg, valid_models)
            if match and match != arg:
                self.do_model(match, _print_on_success=_print_on_success)

    def complete_model(self, text, line, begidx, endidx):
        valid_models = self._account.provider.valid_models or ()
        return [m for m in valid_models if m.startswith(text)]

    def do_set(self, arg):
        """
        Set an API parameter. Pass no arguments to see currently set
        parameters. Valid Python literals are supported (None represents null).
        example: "set temperature 0.9"
        """
        if not arg:
            if not self._account.provider.api_params:
                print("No API parameter definitions")
                return
            for k, v in self._account.provider.api_params.items():
                print(f"{k}: {repr(v)}")
        else:
            t = arg.split()
            key = t[0]
            try:
                val = literal_eval(" ".join(t[1:]))
            except (SyntaxError, ValueError):
                print("Invalid syntax")
                return
            try:
                validated_val = self._account.provider.set_api_param(key, val)
                print(f"{key} set to {validated_val!r}")
            except InvalidAPIParameterError as e:
                print(str(e))

    def complete_set(self, text, line, begidx, endidx):
        KNOWN_OPENAI_API_PARAMS = (  # Add other parameters (not defined as
            # special in MessageThread.set_api_param) to this list if the API
            # changes.
            "temperature",
            "top_p",
            "stop",
            "max_tokens",
            "presence_penalty",
            "frequency_penalty",
            "logit_bias",
            "request_timeout",
        )
        if begidx <= 4:  # In the first argument
            return [
                param
                for param in KNOWN_OPENAI_API_PARAMS
                if param.startswith(text)
            ]

    def do_unset(self, arg):
        """
        Clear the definition of a custom API parameter. Pass no arguments
        to clear all parameters.
        example: "unset timeout"
        """
        try:
            if not arg:
                self._account.provider.unset_api_param(None)
                print("Unset all parameters")
            else:
                self._account.provider.unset_api_param(arg)
                print(f"{arg} unset")
        except InvalidAPIParameterError as e:
            print(e)

    def complete_unset(self, text, line, begidx, endidx):
        return self.__class__._complete_from_key(
            self._account.provider.api_params, text
        )

    def do_stream(self, arg):
        """
        Toggle streaming, which allows responses to be displayed as they are
        generated. This command takes no arguments.
        """
        try:
            self._account.provider.stream = not self._account.provider.stream
            if self._account.provider.stream:
                print("On")
            else:
                print("Off")
        except NotImplementedError as e:
            print(str(e))

    def do_name(self, arg):
        """
        Set a name to send to the language model for all future messages of
        the specified role. First argument is the role
        (user/assistant/system), second is the name to send. Pass no arguments
        to see all set names in this thread.
        example: "name user Bill"
        """
        if not arg:
            for k, v in self._current_thread.names.items():
                print(f"{k}: {v}")
            return
        if (
            LLMProviderFeature.MESSAGE_NAME_FIELD
            not in self._account.provider.SUPPORTED_FEATURES
        ):
            print("Name definition not supported")
            return
        t = arg.split()
        if len(t) != 2 or not self.__class__._validate_role(t[0]):
            print(
                f"Usage: name <{'|'.join(self.__class__.KNOWN_ROLES)}> <new"
                " name>"
            )
            return
        role = MessageRole(t[0])
        name = " ".join(t[1:])
        self._current_thread.names[role] = name
        print(f"{role} set to {name!r}")

    def complete_name(self, text, line, begidx, endidx):
        if begidx <= 5:  # In the first argument
            return self.__class__._complete_role(text)

    def do_unname(self, arg):
        """
        Clear the definition of a name. Pass no arguments to clear all
        names.
        """
        if (
            LLMProviderFeature.MESSAGE_NAME_FIELD
            not in self._account.provider.SUPPORTED_FEATURES
        ):
            print("Name definition not supported")
            return
        if not arg:
            self._current_thread.names = {}
            print("Unset all names")
        name = self._current_thread.names.get(arg)
        if name is None:
            print(f"{arg} not set")
        else:
            del self._current_thread.names[arg]
            print(f"{arg} is no longer {name!r}")

    def complete_unname(self, text, line, begidx, endidx):
        return self.__class__._complete_from_key(
            self._current_thread.names, text
        )

    def do_rename(self, arg):
        """
        Change the name for the specified role over a range of non-sticky
        messages in the current thread. This command takes three arguments:
        the role (user/assistant/system), the range to affect, and an optional
        name (omitting the name clears it).
        examples:
        "rename assistant 1 5 AI" (sets the name to "AI" in any user messages
        in the first through fifth message)
        "rename assistant 1 3" (unsets names on assistant messages in the
        current thread)
        "rename user ." (unsets all names on user messages in the current
        thread)
        """
        m = re.match(
            (
                f"^({'|'.join(self.__class__.KNOWN_ROLES)})\\s+"
                r"((?:-?\d+|\.)(?:\s+-?\d+|\s*\.)*)"
                r"(?:\s+([a-zA-Z0-9_-]{1,64}))?$"
            ),
            arg,
        )
        if not m:
            print(
                f"Usage: rename <{'|'.join(self.__class__.KNOWN_ROLES)}>"
                " <message range> [name]"
            )
            return
        if (
            LLMProviderFeature.MESSAGE_NAME_FIELD
            not in self._account.provider.SUPPORTED_FEATURES
        ):
            print("Name definition not supported")
            return
        role, ref, name = m.groups()
        try:
            start, end = self.__class__._user_range_to_python_range(ref)
        except ValueError:
            print("Invalid rename range")
            return
        t = self._current_thread.rename(
            role=role, name=name, start_index=start, end_index=end
        )
        mp = "message" if len(t) == 1 else "messages"
        print(f"{len(t)} {mp} renamed")

    def complete_rename(self, text, line, begidx, endidx):
        if begidx <= 7:  # In the first argument
            return self.__class__._complete_role(text)

    def do_sticky(self, arg):
        """
        Sticky the messages in the specified range, so that deletion commands
        in the current thread (pop, clear, etc.) and rename do not affect them.
        example: "sticky 1 5"
        """
        try:
            start, end = self.__class__._user_range_to_python_range(arg)
        except ValueError:
            print("Invalid sticky range")
            return
        t = self._current_thread.sticky(start, end, True)
        mp = "message" if len(t) == 1 else "messages"
        print(f"{len(t)} {mp} stickied")

    def do_unsticky(self, arg):
        """
        Unsticky any sticky mesages in the specified range, so that deletion
        and rename commands once again affect them.
        example: "unsticky 1 5"
        """
        try:
            start, end = self.__class__._user_range_to_python_range(arg)
        except ValueError:
            print("Invalid unsticky range")
            return
        t = self._current_thread.sticky(start, end, False)
        mp = "message" if len(t) == 1 else "messages"
        print(f"{len(t)} {mp} unstickied")

    def do_save(
        self,
        arg: str,
        _extra_metadata: Optional[Dict[str, Any]] = None,
        _print_on_success: bool = True,
    ):
        """
        Save all named threads to the specified json file. With no argument,
        save to the most recently loaded/saved JSON file in this session.
        """
        args = self.__class__._lex_args(arg)
        if len(args) > 1:
            print("Usage: save [path]")
            return
        if self._detached.dirty:
            print(
                f"Warning: {len(self._detached)} detached messages will not"
                " be saved. If you wish to save them, create a named"
                " thread."
            )
        if not self._threads:
            print("No threads to save!")
            return
        if not args:
            if self.last_path is None:
                print("No file specified")
                return
            path = self.last_path
        else:
            path = args[0]
        res = {}
        if _extra_metadata is None:
            res["_meta"] = {}
        else:
            res["_meta"] = _extra_metadata.copy()
        res["_meta"]["version"] = __version__
        res["threads"] = {k: v.to_dict() for k, v in self._threads.items()}
        try:
            with open(path, "w", encoding="utf-8") as cam:
                json.dump(res, cam, indent=2)
        except (OSError, UnicodeEncodeError) as e:
            print(str(e))
            return
        for thread in self._threads.values():
            thread.dirty = False
        if _print_on_success:
            print(f"{os.path.abspath(path)} saved")
        self.last_path = path

    def do_load(self, arg, _print_on_success=True):
        "Load all threads from the specified json file."
        if not arg:
            print("Usage: load <path>\n")
            return
        try:
            args = self.__class__._lex_args(arg)
        except ValueError as e:
            print(e)
            return
        if len(args) != 1:
            print("Usage: load <path>")
            return
        path = args[0]
        try:
            with open(path, encoding="utf-8") as fin:
                d = json.load(fin)
        except (
            OSError,
            json.JSONDecodeError,
            UnicodeDecodeError,
        ) as e:
            print(f"Cannot load: {str(e)}")
            return
        if "_meta" not in d:
            print("Cannot load: malformed or very old file!")
            return
        my_major = int(__version__.split(".")[0])
        their_major = int(d["_meta"]["version"].split(".")[0])
        if my_major < their_major:
            print(
                "Cannot load: this file requires Gptcmd version"
                f" {their_major}.0.0 or later!"
            )
            return
        self._threads.update(
            {
                k: self.thread_cls.from_dict(v, name=k)
                for k, v in d["threads"].items()
            }
        )
        if self._current_thread != self._detached:
            # If a thread is loaded with the same name as the current thread,
            # the current thread might become unreachable.
            # Re-sync the current thread with reality.
            self._current_thread = self._threads.get(
                self._current_thread.name, self._detached
            )
        self.last_path = arg
        if _print_on_success:
            print(f"{arg} loaded")

    def do_read(self, arg):
        """
        Read the contents of the file (first argument) as a new message with
        the specified role (second argument).
        example: "read /path/to/prompt.txt system"
        """
        try:
            args = self.__class__._lex_args(arg)
        except ValueError as e:
            print(e)
            return
        if len(args) < 2 or not self.__class__._validate_role(args[-1]):
            print(
                f"Usage: read <path> <{'|'.join(self.__class__.KNOWN_ROLES)}>"
            )
            return
        path = " ".join(args[:-1])
        role = MessageRole(args[-1])
        try:
            with open(path, encoding="utf-8", errors="ignore") as fin:
                self._append_new_message(
                    arg=fin.read(), role=role, _edit_on_empty=False
                )
        except (OSError, UnicodeDecodeError) as e:
            print(str(e))
            return

    def complete_read(self, text, line, begidx, endidx):
        if begidx > 5:  # Passed the first argument
            return self.__class__._complete_role(text)

    def do_write(self, arg):
        "Write the contents of the last message to the specified file."
        try:
            args = self.__class__._lex_args(arg)
        except ValueError as e:
            print(e)
            return
        if len(args) != 1:
            print("Usage: write <path>")
            return
        path = args[0]
        try:
            with open(path, "w", encoding="utf-8", errors="ignore") as cam:
                msg = self._current_thread.messages[-1]
                cam.write(msg.content)
                print(
                    self.__class__._fragment(
                        "{msg} written to " + os.path.abspath(path), msg
                    )
                )
        except (OSError, UnicodeEncodeError) as e:
            print(str(e))
            return

    def complete_write(self, text, line, begidx, endidx):
        if begidx > 6:  # Passed the first argument
            return self.__class__._complete_role(text)

    def do_transcribe(self, arg):
        """
        Write the entire thread (as a human-readable transcript) to the
        specified file.
        """
        try:
            args = self.__class__._lex_args(arg)
        except ValueError as e:
            print(e)
            return
        if len(args) != 1:
            print("Usage: transcribe <path>")
            return
        path = args[0]
        try:
            with open(path, "w", encoding="utf-8", errors="ignore") as cam:
                cam.write(
                    self._current_thread.render(display_indicators=False)
                )
            print(f"Transcribed to {os.path.abspath(path)}")
        except (OSError, UnicodeEncodeError) as e:
            print(str(e))
            return

    def _attachment_url_helper(
        self,
        cmd_name: str,
        attachment_type: Type[MessageAttachment],
        arg: str,
        success_callback: Optional[Callable[[Message], None]] = None,
    ):
        USAGE = f"Usage: {cmd_name} <location> [message]"
        m = re.match(r"^(.*?)(?:\s(-?\d+))?$", arg)
        if not m:
            print(USAGE)
            return
        location, ref = m.groups()
        if not location or location.isspace():
            print(USAGE)
            return
        try:
            idx = (
                -1
                if ref is None
                else self.__class__._user_range_to_python_range(ref)[0]
            )
        except ValueError:
            print("Invalid message specification")
            return
        try:
            if location.startswith("http"):
                a = attachment_type(url=location)
            else:
                a = attachment_type.from_path(
                    self.__class__._lex_args(location)[0]
                )
        except (OSError, ValueError) as e:
            print(e)
            return
        try:
            msg = self._current_thread[idx]
            msg.attachments.append(a)
            if success_callback:
                success_callback(msg)
            print(
                self.__class__._fragment(
                    f"{attachment_type.__name__} added to {{msg}}", msg
                )
            )
        except IndexError:
            print("Message doesn't exist")
            return

    def do_image(self, arg):
        "Attach an image at the specified location"
        return self._attachment_url_helper(
            cmd_name="image", attachment_type=Image, arg=arg
        )

    def do_audio(self, arg):
        "Attach an audio file at the specified location"

        def _success(msg):
            if (
                self._account.provider.model
                and "audio" not in self._account.provider.model
                and "gpt-4o-audio-preview"
                in (self._account.provider.valid_models or ())
            ):
                print(
                    "Warning! The selected model may not support audio. "
                    "If sending this conversation fails, try switching to an "
                    "audio-capable model with:\nmodel gpt-4o-audio-preview"
                )

        return self._attachment_url_helper(
            cmd_name="audio",
            attachment_type=Audio,
            arg=arg,
            success_callback=_success,
        )

    def do_account(self, arg, _print_on_success: bool = True):
        "Switch between configured accounts."
        if not arg:
            others = [
                v.name
                for v in self.config.accounts.values()
                if v != self._account
            ]
            print(f"Active account: {self._account.name}")
            if others:
                print(f"Available accounts: {', '.join(others)}")
            return
        if arg in self.config.accounts:
            candidate = self.config.accounts[arg]
            try:
                _ = candidate.provider  # Attempt to instantiate
            except ConfigError as e:
                print(str(e))
                return
            self._account = candidate
            if _print_on_success:
                print(f"Switched to account {self._account.name!r}")
        else:
            print(f"{arg} is not configured")

    def complete_account(self, text, line, begidx, endidx):
        return self.__class__._complete_from_key(self.config.accounts, text)

    def _edit_interactively(
        self, initial_text: str, filename_prefix: str = "gptcmd"
    ) -> Optional[str]:
        try:
            with tempfile.NamedTemporaryFile(
                prefix=filename_prefix,
                mode="w",
                delete=False,
                encoding="utf-8",
                errors="ignore",
            ) as cam:
                cam.write(initial_text)
                tempname = cam.name
        except (OSError, UnicodeEncodeError) as e:
            print(e)
            return None
        except KeyboardInterrupt:
            return None
        try:
            mtime_before = os.path.getmtime(tempname)
            subprocess.run((*self.config.editor, tempname), check=True)
            mtime_after = os.path.getmtime(tempname)
            if mtime_after == mtime_before:
                # File was not changed
                return None
            with open(tempname, encoding="utf-8") as fin:
                return fin.read()
        except FileNotFoundError:
            editor_cmd = " ".join(self.config.editor)
            print(f"Editor {editor_cmd} could not be found")
            return None
        except (
            UnicodeDecodeError,
            subprocess.CalledProcessError,
            ConfigError,
        ) as e:
            print(e)
            return None
        except KeyboardInterrupt:
            return None
        finally:
            # Clean up the temporary file
            os.unlink(tempname)

    def do_edit(self, arg):
        """
        Opens the content of the specified message in an external editor for
        modification. With no argument, edits the last message.
        """
        try:
            idx = (
                -1
                if not arg
                else self.__class__._user_range_to_python_range(arg)[0]
            )
        except ValueError:
            print(
                "Usage: edit[message]\n"
                "With no argument, the edit command edits the last message. "
                "With a message number provided as an argument, the edit "
                "command edits that message."
            )
            return
        try:
            msg = self._current_thread.messages[idx]
            new = self._edit_interactively(msg.content)
            if new:
                msg.content = new
                print("Edited")
            else:
                print("Cancelled")
        except IndexError:
            print("Message doesn't exist")

    def do_grep(self, arg):
        """
        Search the current thread for messages whose content matches the
        supplied regex.
        """
        if not arg:
            print("Usage: grep <regex>")
            return
        try:
            expr = re.compile(arg)
        except re.error as e:
            print(e)
            return

        def _show(content: str, m: re.Match, width: int = 40) -> str:
            start = max(0, m.start() - width)
            end = min(len(content), m.end() + width)
            res = content[start:end]
            if start > 0:
                res = "..." + res
            if end < len(content):
                res += "..."
            return expr.sub(lambda x: f"[{x.group(0)}]", res)

        found = False
        for idx, msg in enumerate(self._current_thread.messages, start=1):
            if not (m := expr.search(msg.content)):
                continue
            if m.end() == m.start():
                continue
            preview = self.__class__._fragment(
                "{msg}", Message(content=_show(msg.content, m), role=msg.role)
            )
            name = msg.name if msg.name else msg.role
            print(f"{msg.display_indicators}{idx} ({name}): {preview}")
            found = True

        if not found:
            print("No hits!")

    def _parse_meta_args(
        self, arg: str
    ) -> Tuple["Message", Optional[str], Optional[str]]:
        arg = arg.strip()
        if not arg:
            # bare `meta` / `unmeta` operate on last message
            return (self._current_thread[-1], None, None)

        tokens = arg.split()

        idx_token = None
        if tokens and (tokens[0] == "." or tokens[0].lstrip("-").isdigit()):
            idx_token = tokens.pop(0)

        if idx_token is None:
            idx = -1
        else:
            start, _ = self.__class__._user_range_to_python_range(
                idx_token, allow_single=True
            )
            idx = -1 if start is None else start

        # will raise IndexError if message is absent, handled by caller
        target_msg = self._current_thread[idx]

        if not tokens:
            return (target_msg, None, None)

        key = tokens.pop(0)
        val = " ".join(tokens) if tokens else None
        return (target_msg, key, val)

    def do_meta(self, arg):
        """
        Get or set metadata on a message.
        """
        USAGE = "Usage: meta [message] <key> [value]"
        try:
            msg, key, val = self._parse_meta_args(arg)
        except ValueError:
            print(USAGE)
            return
        except IndexError:
            print("message doesn't exist")
            return

        if key is None:
            if msg.metadata:
                for k, v in msg.metadata.items():
                    print(f"{k}: {v!r}")
            else:
                print(
                    self.__class__._fragment("No metadata set on {msg}", msg)
                )
            return

        if val is None:
            print(repr(msg.metadata.get(key, f"{key} not set")))
            return

        try:
            validated_val = self.__class__._json_eval(val)
        except (json.JSONDecodeError, UnicodeDecodeError):
            print("Invalid syntax")
            return
        msg.metadata[key] = validated_val
        self._current_thread.dirty = True

        printable_val = (
            repr(validated_val).replace("{", "{{").replace("}", "}}")
        )
        print(
            self.__class__._fragment(
                f"{key} set to {printable_val} on {{msg}}", msg
            )
        )

    def complete_meta(self, text, line, begidx, endidx):
        if text.lstrip("-").isdigit():
            return []
        try:
            msg = self._current_thread[-1]
            return self.__class__._complete_from_key(msg.metadata, text)
        except IndexError:
            return []

    def do_unmeta(self, arg):
        """
        Delete a metadata key from a message.
        """
        USAGE = "Usage: unmeta [message] <key>"
        try:
            msg, key, val = self._parse_meta_args(arg)
        except ValueError:
            print(USAGE)
            return
        except IndexError:
            print("message doesn't exist")
            return
        if val is not None:  # malformed syntax
            print(USAGE)
            return
        if key is None:
            if not msg.metadata:
                print(
                    self.__class__._fragment("No metadata set on {msg}", msg)
                )
                return
            n = len(msg.metadata)
            items = "item" if n == 1 else "items"
            prompt = self.__class__._fragment(
                f"delete {n} {items} on {{msg}}?", msg
            )
            if not self.__class__._confirm(prompt):
                return
            msg.metadata.clear()
            self._current_thread.dirty = True
            print(self.__class__._fragment("Unset all metadata on {msg}", msg))
            return
        if key in msg.metadata:
            msg.metadata.pop(key)
            self._current_thread.dirty = True
            print(self.__class__._fragment(f"{key} unset on {{msg}}", msg))
        else:
            print(self.__class__._fragment(f"{key} not set on {{msg}}", msg))

    def complete_unmeta(self, text, line, begidx, endidx):
        try:
            msg = self._current_thread[-1]
            return self.__class__._complete_from_key(msg.metadata, text)
        except IndexError:
            return []

    def do_quit(self, arg):
        "Exit the program."
        warn = ""
        if self._detached.dirty:
            warn += "All unsaved detached messages will be lost.\n"
        for threadname, thread in self._threads.items():
            if thread.dirty:
                warn += f"{threadname} has unsaved changes.\n"
        if warn:
            can_exit = self.__class__._confirm(
                f"{warn}\nAre you sure that you wish to exit?"
            )
        else:
            can_exit = True
        if can_exit:
            self._future_executor.shutdown(wait=False)
        return can_exit  # Truthy return values cause the cmdloop to stop


def _write_crash_dump(shell: Gptcmd, exc: Exception) -> Optional[str]:
    """
    Serialize the current shell into a JSON file and return its absolute
    path.
    """
    detached_added = False
    try:
        ts = (
            datetime.datetime.now()
            .isoformat(timespec="seconds")
            .replace(":", "-")
        )
        filename = f"gptcmd-{ts}.json"
        tb_text = "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        )
        if shell._detached:
            original_dirty = shell._detached.dirty
            detached_base = "__detached__"
            detached_key = detached_base
            i = 1
            while detached_key in shell._threads:
                i += 1
                detached_key = f"{detached_base}{i}"
            shell._detached.dirty = False
            shell._threads[detached_key] = shell._detached
            detached_added = True
        shell.do_save(
            filename,
            _extra_metadata={"crash_traceback": tb_text},
            _print_on_success=False,
        )
        return os.path.abspath(filename)
    except Exception as e:
        print(f"Failed to write crash dump: {e}", file=sys.stderr)
        return None
    finally:
        if detached_added:
            shell._detached.dirty = original_dirty
            shell._threads.pop(detached_key, None)


def main() -> bool:
    """
    Setuptools requires a callable entry point to build an installable script
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "path",
        help="The path to a JSON file of named threads to load on launch",
        nargs="?",
    )
    parser.add_argument(
        "-c",
        "--config",
        help="The path to a Gptcmd configuration file to use for this session",
    )
    parser.add_argument(
        "-t",
        "--thread",
        help="The name of the thread to switch to on launch",
    )
    parser.add_argument(
        "-m",
        "--model",
        help="The name of the model to switch to on launch",
    )
    parser.add_argument(
        "-a",
        "--account",
        help="The name of the account to switch to on launch",
    )
    parser.add_argument(
        "--version", help="Show version and exit", action="store_true"
    )
    args = parser.parse_args()
    if args.version:
        print(f"Gptcmd {__version__}")
        return True
    try:
        if args.config:
            config = ConfigManager.from_toml(args.config)
        else:
            config = None
        shell = Gptcmd(config=config)
    except ConfigError as e:
        print(f"Couldn't read config: {e}")
        return False
    if args.path:
        shell.do_load(args.path, _print_on_success=False)
    if args.thread:
        shell.do_thread(args.thread, _print_on_success=False)
    if args.account:
        shell.do_account(args.account, _print_on_success=False)
    if args.model:
        shell.do_model(args.model, _print_on_success=False)
    try:
        shell.cmdloop()
    except SystemExit:
        # Don't write a crash dump
        raise
    except BaseException as e:
        # Does any thread contain messages?
        should_save = (shell._detached and shell._detached.dirty) or any(
            t and t.dirty for t in shell._threads.values()
        )
        if should_save:
            dump_path = _write_crash_dump(shell, e)
            if dump_path:
                # Hack: Print the "crash dump" notice after the traceback
                atexit.register(
                    lambda p=dump_path: print(
                        f"Crash dump written to {p}",
                        file=sys.stderr,
                        flush=True,
                    )
                )
        raise
    return True


if __name__ == "__main__":
    success = main()
    if success:
        sys.exit(0)
    else:
        sys.exit(1)
