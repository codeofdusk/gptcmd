"""
This module contains the Gptcmd class and serves as an entry point to the
Gptcmd command line application.
Copyright 2024 Bill Dengler
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""

import argparse
import cmd
import dataclasses
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from ast import literal_eval
from textwrap import shorten
from typing import (
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
)

from .config import ConfigError, ConfigManager
from .llm import CompletionError, InvalidAPIParameterError, LLMProviderFeature
from .message import (
    Image,
    Message,
    MessageRole,
    MessageThread,
    PopStickyMessageError,
)


__version__ = "2.0.0"


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
        self._account = self.config.default_account
        self._detached = self.thread_cls("*detached*")
        self._current_thread = self._detached
        self._threads = {}
        self._session_cost_in_cents = 0
        self._session_cost_incomplete = False
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
        width = MAX_LENGTH - len(tpl.format(msg=""))
        content = msg.content
        res = shorten(content, width=width, placeholder=PLACEHOLDER)
        if res == PLACEHOLDER:
            # This isn't a very useful representation.
            # Go over slightly, even if the result is a bit more awkward.
            res = content[:width] + "..."
        return tpl.format(msg=repr(res))

    @staticmethod
    def _user_range_to_python_range(
        ref: str,
    ) -> Tuple[Optional[int], Optional[int]]:
        c = ref.count(" ")
        if c == 0:
            if ref == ".":
                return (None, None)
            start = end = ref
        elif c == 1:
            start, end = ref.split()
        else:
            raise ValueError("Wrong number of indices")

        if start == ".":
            py_start = None
        else:
            py_start = int(start)
            if py_start > 0:
                py_start -= 1  # Python indices are zero-based
        if end == ".":
            py_end = None
        else:
            py_end = int(end)
            if py_end > 0:
                py_end -= 1  # Python indices are zero-based
                py_end += 1  # Python indices are end exclusive
            elif py_end == -1:
                py_end = None
            else:
                py_end += 1  # Python indices are end exclusive

        if c == 0:
            # Don't return an empty range
            if py_start == -1:
                py_end = None
            elif py_start is not None:
                py_end = py_start + 1

        if py_start is not None and py_end is not None and py_start >= py_end:
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

    KNOWN_ROLES = tuple(MessageRole)

    @classmethod
    def _complete_role(cls, text: str) -> List[str]:
        return [role for role in cls.KNOWN_ROLES if role.startswith(text)]

    @classmethod
    def _validate_role(cls, role: str) -> bool:
        return role in cls.KNOWN_ROLES

    def emptyline(self):
        "Disable Python cmd's repeat last command behaviour."
        pass

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
        try:
            res = self._account.provider.complete(self._current_thread)
        except KeyboardInterrupt:
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
            i, j = self._user_range_to_python_range(arg)
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
            self.do_thread(basename + str(num))
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
        elif arg in self._account.provider.valid_models:
            self._account.provider.model = arg
            if _print_on_success:
                print(f"Switched to model {self._account.provider.model!r}")
        else:
            print(f"{arg} is currently unavailable")

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

    def do_save(self, arg):
        """
        Save all named threads to the specified json file. With no argument,
        save to the most recently loaded/saved JSON file in this session.
        """
        args = shlex.split(arg)
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
        res["_meta"] = {"version": __version__}
        res["threads"] = {k: v.to_dict() for k, v in self._threads.items()}
        try:
            with open(path, "w", encoding="utf-8") as cam:
                json.dump(res, cam, indent=2)
        except (OSError, UnicodeEncodeError) as e:
            print(str(e))
            return
        for thread in self._threads.values():
            thread.dirty = False
        print(f"{os.path.abspath(path)} saved")
        self.last_path = path

    def do_load(self, arg, _print_on_success=True):
        "Load all threads from the specified json file."
        if not arg:
            print("Usage: load <path>\n")
            return
        try:
            args = shlex.split(arg)
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
            FileNotFoundError,
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
            args = shlex.split(arg)
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
        except (FileNotFoundError, OSError, UnicodeDecodeError) as e:
            print(str(e))
            return

    def complete_read(self, text, line, begidx, endidx):
        if begidx > 5:  # Passed the first argument
            return self.__class__._complete_role(text)

    def do_write(self, arg):
        "Write the contents of the last message to the specified file."
        try:
            args = shlex.split(arg)
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
            args = shlex.split(arg)
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

    def do_image(self, arg):
        "Attach an image at the specified location"
        USAGE = "Usage: image <location> [message]"
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
        if location.startswith("http"):
            img = Image(url=location)
        else:
            try:
                img = Image.from_path(shlex.split(location)[0])
            except (OSError, FileNotFoundError, ValueError) as e:
                print(e)
                return
        try:
            msg = self._current_thread[idx]
            msg.attachments.append(img)
            if (
                not (
                    "gpt-4-turbo" in self._account.provider.model
                    or "gpt-4o" in self._account.provider.model
                    or "vision" in self._account.provider.model
                )
                and "gpt-4-turbo" in self._account.provider.valid_models
            ):
                print(
                    "Warning! The selected model may not support vision. "
                    "If sending this conversation fails, try switching to a "
                    "vision-capable model with the following command:\n"
                    "model gpt-4-turbo"
                )
            print(self.__class__._fragment("Image added to {msg}", msg))
        except IndexError:
            print("Message doesn't exist")
            return

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
            self._account = self.config.accounts[arg]
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
            ) as cam:
                cam.write(initial_text)
                tempname = cam.name
        except (FileNotFoundError, OSError, UnicodeEncodeError) as e:
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
        return can_exit  # Truthy return values cause the cmdloop to stop


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
    shell.cmdloop()
    return True


if __name__ == "__main__":
    success = main()
    if success:
        sys.exit(0)
    else:
        sys.exit(1)
