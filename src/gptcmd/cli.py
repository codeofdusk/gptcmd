import argparse
import cmd
import json
import openai
import os
import re
import sys

from ast import literal_eval
from .message import (
    APIParameterError,
    CostEstimateUnavailableError,
    Message,
    MessageStream,
    MessageThread,
    PopStickyMessageError,
)
from textwrap import shorten
from typing import (
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
)


"""
This module contains the Gptcmd class and serves as an entry point to the
Gptcmd command line application.
Copyright 2023 Bill Dengler
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""


__version__ = "1.0.3"


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

    def __init__(self, *args, **kwargs):
        self.last_path = None
        self._detached = MessageThread("*detached*")
        self._current_thread = self._detached
        self._threads = {}
        super().__init__(*args, **kwargs)

    @property
    def prompt(self):
        threadname = (
            ""
            if self._current_thread == self._detached
            else self._current_thread.name
        )
        return f"{threadname}({self._current_thread.model}) "

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
            start = end = ref
        elif c == 1:
            start, end = ref.split()
        else:
            raise ValueError("Wrong number of indices")
        if start == ".":
            py_start = None
        else:
            py_start = int(start)
        if end == ".":
            py_end = None
        else:
            py_end = int(end)
        if py_start is not None and py_start > 0:
            py_start -= 1
        if py_start is not None and py_start < 0 and py_start == py_end:
            # In Python, specifying a negative index twice returns an empty
            # slice. Unset the end to maintain parity with positive indexing.
            py_end = None
        return (py_start, py_end)

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

    KNOWN_ROLES = ("user", "assistant", "system")

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
            self._threads[arg] = MessageThread(
                name=arg,
                model=self._current_thread.model,
                messages=self._current_thread.messages,
                api_params=self._current_thread.api_params,
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

    def do_user(self, arg):
        """
        Append a new user message (with content provided as argument) to the
        current thread.
        example: "user Hello, world!"
        """
        self._current_thread.append(Message(content=arg, role="user"))
        print("OK")

    def do_assistant(self, arg):
        """
        Append a new assistant message (with content provided as argument) to
        the current thread.
        example: "assistant how can I help?"
        """
        self._current_thread.append(Message(content=arg, role="assistant"))
        print("OK")

    def do_system(self, arg):
        """
        Append a new system message (with content provided as argument) to
        the current thread.
        example: "system You are a friendly assistant."
        """
        self._current_thread.append(Message(content=arg, role="system"))
        print("OK")

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
        Send the current thread to GPT, and print the response. This command
        takes no arguments.
        """
        print("...")
        try:
            res = self._current_thread.send()
        except KeyboardInterrupt:
            return
        except (NotImplementedError, openai.OpenAIError) as e:
            print(str(e))
            return
        if isinstance(res, Message):
            print(res.content)
        elif isinstance(res, MessageStream):
            try:
                for chunk in res:
                    if "content" in chunk:
                        print(chunk["content"], end="")
                print("\n", end="")
            except KeyboardInterrupt:
                print("\nDisconnected from stream")
                return
        cost_threads = (self._detached, *self._threads.values())
        try:
            dollars, cents = divmod(
                sum(th.cost_cents for th in cost_threads), 100
            )
            prompt_tokens = sum(th.prompt_tokens for th in cost_threads)
            sampled_tokens = sum(th.sampled_tokens for th in cost_threads)
            print(
                f"Estimated session cost: ${dollars}.{cents:02d}"
                f" ({prompt_tokens} prompt, {sampled_tokens} sampled)"
            )
        except CostEstimateUnavailableError:
            pass

    def do_say(self, arg):
        """
        Append a new user message (with content provided as argument) to the
        current thread, then send the thread to GPT and print the response.
        example: "say Hello!"
        """
        self._current_thread.append(Message(content=arg, role="user"))
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
            print("OK")

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
                print("OK")
        elif arg in self._threads:
            if self._threads[arg] == self._current_thread:
                self._current_thread = self._detached
            del self._threads[arg]
            print("OK")
        else:
            print(f"{arg} doesn't exist")

    def complete_delete(self, text, line, begidx, endidx):
        return self.__class__._complete_from_key(self._threads, text)

    def do_flip(self, arg):
        """
        Move the last message to the start of the thread. This command takes
        no arguments.
        """
        try:
            msg = self._current_thread.flip()
        except PopStickyMessageError:
            print("That message is sticky; unsticky it first")
            return
        print(self.__class__._fragment("{msg} moved to start", msg))

    def do_slice(self, arg):
        """
        Copy the range of messages provided as argument to the detached thread.
        example: "slice 1 3"
        """
        try:
            start, end = self.__class__._user_range_to_python_range(arg)
        except ValueError:
            print("Invalid slice")
            return
        s = self._current_thread[start:end]
        if not s:
            print("Empty slice")
            return
        if len(s) == 1:
            print(
                self.__class__._fragment(
                    "Slice contains one message: {msg}", s[0]
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
        if self._detached.dirty:
            print("Unsaved detached messages will be lost.")
        can_slice = self.__class__._confirm("Confirm slice?")
        if not can_slice:
            return
        self._detached.messages = s
        print("OK")

    def do_retry(self, arg):
        """
        Resend up through the last non-assistant, non-sticky message to GPT.
        This command takes no arguments.
        """
        if not self._current_thread:
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
        while self._current_thread[-1].role == "assistant":
            try:
                self._current_thread.pop()
            except PopStickyMessageError:
                print(
                    self.__class__._fragment(
                        "Sending up to sticky message {msg}",
                        self._current_thread[-1],
                    )
                )
                break
        self.do_send(None)

    def do_model(self, arg):
        """
        Change the GPT model used by the current thread. Pass no argument to
        check the currently active model.
        example: "model gpt-3.5-turbo"
        """
        if not arg:
            print(f"Current model: {self._current_thread.model}")
        elif self._current_thread._is_valid_model(arg):
            self._current_thread.model = arg
            print("OK")
        else:
            print(f"{arg} is currently unavailable")

    def do_set(self, arg):
        """
        Set a GPT API parameter. Pass no arguments to see currently set
        parameters. Valid Python literals are supported (None represents null).
        example: "set temperature 0.9"
        """
        if not arg:
            for k, v in self._current_thread._api_params.items():
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
                self._current_thread.set_api_param(key, val)
                print("OK")
            except APIParameterError as e:
                print(str(e))

    def complete_set(self, text, line, begidx, endidx):
        KNOWN_OPENAI_API_PARAMS = (  # Add other parameters (not defined as
            # special in MessageThread.set_api_param) to this list if the API
            # changes.
            "temperature",
            "top_p",
            "n",
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
        Clear the definition of a custom GPT API parameter. Pass no arguments
        to clear all parameters.
        example: "unset response_timeout"
        """
        if not arg:
            self._current_thread._api_params = (
                MessageThread.DEFAULT_API_PARAMS.copy()
            )
            print("Unset all parameters")
        elif arg not in self._current_thread._api_params:
            print(f"{arg} not set")
        elif arg in MessageThread.DEFAULT_API_PARAMS:
            self._current_thread.set_api_param(
                arg, MessageThread.DEFAULT_API_PARAMS[arg]
            )
            print("Unset")
        else:
            del self._current_thread._api_params[arg]
            print("Unset")

    def complete_unset(self, text, line, begidx, endidx):
        return self.__class__._complete_from_key(
            self._current_thread.api_params, text
        )

    def do_stream(self, arg):
        """
        Toggle streaming, which allows responses to be displayed as they are
        generated. This command takes no arguments.
        """
        self._current_thread.stream = not self._current_thread.stream
        if self._current_thread.stream:
            print("On")
        else:
            print("Off")

    def do_name(self, arg):
        """
        Set a name to send to GPT for all future messages of the specified
        role. First argument is the role (user/assistant/system), second is
        the name to send. Pass no arguments to see all set names in this
        thread.
        example: "name user Bill"
        """
        if not arg:
            for k, v in self._current_thread.names.items():
                print(f"{k}: {v}")
            return
        t = arg.split()
        if len(t) != 2:
            print("Usage: name <user|assistant|system> <new name>")
            return
        role = t[0]
        name = " ".join(t[1:])
        self._current_thread.names[role] = name
        print("OK")

    def complete_name(self, text, line, begidx, endidx):
        if begidx <= 5:  # In the first argument
            return self.__class__._complete_role(text)

    def do_unname(self, arg):
        """
        Clear the definition of a GPT name. Pass no arguments to clear all
        names.
        """
        if not arg:
            self._current_thread.names = {}
            print("Unset all names")
        elif arg not in self._current_thread.names:
            print(f"{arg} not set")
        else:
            del self._current_thread.names[arg]
            print("Unnamed")

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
        role, ref, name = m.groups()
        try:
            start, end = self.__class__._user_range_to_python_range(ref)
        except ValueError:
            print("Invalid rename range")
            return
        self._current_thread.rename(
            role=role, name=name, start_index=start, end_index=end
        )
        print("OK")

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
        self._current_thread.sticky(start, end, True)
        print("OK")

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
        self._current_thread.sticky(start, end, False)
        print("OK")

    def do_save(self, arg):
        """
        Save all named threads to the specified json file. With no argument,
        save to the most recently loaded/saved JSON file in this session.
        """
        if self._detached.dirty:
            print(
                f"Warning: {len(self._detached)} detached messages will not"
                " be saved. If you wish to save them, create a named"
                " thread."
            )
        if not self._threads:
            print("No threads to save!")
            return
        if not arg:
            if self.last_path is None:
                print("No file specified")
                return
            arg = self.last_path
            print(f"Saving to {os.path.abspath(arg)}")
        res = {}
        res["_meta"] = {"version": __version__}
        res["threads"] = {k: v.to_dict() for k, v in self._threads.items()}
        try:
            with open(arg, "w", encoding="utf-8") as cam:
                json.dump(res, cam, indent=2)
        except (OSError, UnicodeDecodeError) as e:
            print(str(e))
            return
        for thread in self._threads.values():
            thread.dirty = False
        self.last_path = arg
        print("OK")

    def do_load(self, arg, _print_on_success=True):
        "Load all threads from the specified json file."
        if not arg:
            print("Usage: load <path>\n")
            return
        try:
            with open(arg, encoding="utf-8") as fin:
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
                k: MessageThread.from_dict(
                    v, name=k, model=self._current_thread.model
                )
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
            print("OK")

    def do_read(self, arg):
        """
        Read the contents of the file (first argument) as a new message with
        the specified role (second argument).
        example: "read /path/to/prompt.txt system"
        """
        args = arg.split()
        if len(args) < 2 or not self.__class__._validate_role(args[-1]):
            print(
                f"Usage: read <path> <{'|'.join(self.__class__.KNOWN_ROLES)}>"
            )
            return
        path = " ".join(args[:-1])
        role = args[-1]
        try:
            with open(path, encoding="utf-8", errors="ignore") as fin:
                self._current_thread.append(
                    Message(content=fin.read(), role=role)
                )
        except (FileNotFoundError, OSError, UnicodeDecodeError) as e:
            print(str(e))
            return
        print("OK")

    def complete_read(self, text, line, begidx, endidx):
        if begidx > 5:  # Passed the first argument
            return self.__class__._complete_role(text)

    def do_write(self, path):
        "Write the contents of the last message to the specified file."
        if not path:
            print("Usage: write <path>")
            return
        try:
            with open(path, "w", encoding="utf-8", errors="ignore") as cam:
                cam.write(self._current_thread.messages[-1].content)
        except (OSError, UnicodeDecodeError) as e:
            print(str(e))
            return
        print("OK")

    def complete_write(self, text, line, begidx, endidx):
        if begidx > 6:  # Passed the first argument
            return self.__class__._complete_role(text)

    def do_transcribe(self, path):
        """
        Write the entire thread (as a human-readable transcript) to the
        specified file.
        """
        try:
            with open(path, "w", encoding="utf-8", errors="ignore") as cam:
                cam.write(
                    self._current_thread.render(display_indicators=False)
                )
        except (OSError, UnicodeDecodeError) as e:
            print(str(e))
            return
        print("OK")

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
            sys.exit(0)


def main():
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
        "-t",
        "--thread",
        help="The name of the thread to switch to on launch",
    )
    parser.add_argument(
        "--version", help="Show version and exit", action="store_true"
    )
    args = parser.parse_args()
    if args.version:
        print(f"Gptcmd {__version__}")
        return
    shell = Gptcmd()
    if args.path:
        shell.do_load(args.path, _print_on_success=False)
    if args.thread:
        shell.do_thread(args.thread, _print_on_success=False)
    shell.cmdloop()


if __name__ == "__main__":
    main()
