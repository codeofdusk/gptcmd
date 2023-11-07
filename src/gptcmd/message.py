import dataclasses
import inspect

import openai

from collections.abc import Sequence
from typing import (
    Any,
    Dict,
    Iterable,
    List,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
)


"""
This module contains classes and types for interacting with messages, message
threads, and the OpenAI API.
Copyright 2023 Bill Dengler
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""


@dataclasses.dataclass
class Message:
    """A message sent to or received from OpenAI."""

    #: The text content of the message
    content: str
    #: One of "user", "assistant", or "system" defining the conversational
    #: role of the author of this message
    role: str
    #: The name of the author of this message
    name: Optional[str] = None
    #: Whether this message is "sticky" (not affected by thread-level deletion
    #: operations)
    _sticky: bool = False


class _stream:
    """
    A base class for streaming message objects that should not be
    instantiated directly.
    """

    def __init__(self, backing_stream):
        self._stream = backing_stream
        #: A Message containing all content streamed so far
        self.message = Message(content="", role="")

    def _handle_chunk(self, chunk) -> Dict[str, Any]:
        delta = {
            k: v
            for k, v in chunk.choices[0].delta.model_dump().items()
            if v is not None
        }
        for k, v in delta.items():
            if hasattr(self.message, k):
                setattr(self.message, k, getattr(self.message, k) + v)
        return dict(delta)


class MessageStream(_stream):
    "An iterator representing an in-progress message from GPT"

    def __iter__(self):
        return self

    def __next__(self) -> Dict[str, Any]:
        chunk = next(self._stream)
        return self._handle_chunk(chunk)


class AioMessageStream(_stream):
    """
    An iterator representing an in-progress message from GPT that was
    requested using MessageThread.asend
    """

    def __aiter__(self):
        return self

    async def __anext__(self) -> Dict[str, Any]:
        chunk = await anext(self._stream)
        return self._handle_chunk(chunk)


class CostEstimateUnavailableError(Exception):
    "Thrown when a MessageThread's cost cannot be estimated"
    pass


class PopStickyMessageError(Exception):
    "Thrown when attempting to pop a Message marked sticky"
    pass


class APIParameterError(Exception):
    "Thrown when an API parameter cannot be set"
    pass


class MessageThread(Sequence):
    DEFAULT_API_PARAMS: Dict[str, Any] = {"temperature": 0.6}

    def __init__(
        self,
        name: str,
        model: Optional[str] = None,
        messages: Optional[Iterable[Message]] = None,
        api_params: Optional[Dict[str, Any]] = None,
        names: Optional[Dict[str, str]] = None,
    ):
        """A conversation thread between an end-user and GPT

        args:
            name: The display name of this thread
            model: The OpenAI model to use
                (or None to choose the best available)
            messages: An iterable of Message objects from which to populate
                this thread
            api_params: OpenAI API parameters (such as temperature) to set
            names: Mapping of OpenAI roles to names that should be set on
                future messages added to this thread
        """

        self.name: str = name
        self._messages: List[Message] = (
            [dataclasses.replace(m) for m in messages]
            if messages is not None
            else []
        )
        self.names: Dict[str, str] = names if names is not None else {}
        self.dirty: bool = False
        self.prompt_tokens: Optional[int] = 0
        self.sampled_tokens: Optional[int] = 0
        self._api_params: Dict[str, Any] = (
            MessageThread.DEFAULT_API_PARAMS.copy()
        )
        if api_params is not None:
            for key, val in api_params.items():
                try:
                    self.set_api_param(key, val)
                except APIParameterError:
                    continue
        self.stream: bool = False
        self._openai = openai.OpenAI()
        self._async_openai: Optional[openai.AsyncOpenAI] = (
            None  # Lazily create as not used in the CLI
        )
        if model is None:
            models = self._openai.models.list().data
            if self._is_valid_model("gpt-4", models=models):
                self.model = "gpt-4"
            elif self._is_valid_model("gpt-3.5-turbo", models=models):
                self.model = "gpt-3.5-turbo"
            else:
                raise RuntimeError("No known GPT model available!")
        else:
            self.model = model

    @classmethod
    def from_dict(
        cls, d: Dict[str, Any], name: str, model: Optional[str] = None
    ):
        """
        Instantiate a MessageThread from a dict in the format returned by
        MessageThread.to_dict()
        """
        messages = [Message(**m) for m in d.get("messages", [])]
        api_params = d.get("api_params")
        names = d.get("names")
        res = cls(
            name=name,
            messages=messages,
            api_params=api_params,
            names=names,
            model=model,
        )
        return res

    def _is_valid_model(
        self,
        model: str,
        models: Optional[List[openai.types.model.Model]] = None,
    ) -> bool:
        if models is None:
            models = self._openai.models.list().data
        return model in {m.id for m in models}

    def __repr__(self) -> str:
        return f"<{self.name} MessageThread {self._messages!r}>"

    def __getitem__(self, n):
        return self._messages[n]

    def __len__(self, *args, **kwargs) -> int:
        return self._messages.__len__(*args, **kwargs)

    @property
    def api_params(self) -> Dict[str, Any]:
        "The user-defined OpenAI API parameters in this thread"
        return {
            k: v
            for k, v in self._api_params.items()
            if not (
                k in MessageThread.DEFAULT_API_PARAMS
                and self._api_params[k] == MessageThread.DEFAULT_API_PARAMS[k]
            )
        }

    @property
    def messages(self) -> Tuple[Message, ...]:
        return tuple(self._messages)

    @messages.setter
    def messages(self, val: Iterable[Message]):
        self._messages = list(val)
        self.dirty = True

    @property
    def cost_cents(self) -> int:
        "The estimated cost (in cents) of OpenAI API calls from this thread"
        if self.prompt_tokens is None or self.sampled_tokens is None:
            raise CostEstimateUnavailableError(
                "Unable to calculate token usage"
            )
        if self.model.startswith("gpt-4"):
            return (3 * (self.prompt_tokens // 1000)) + (
                6 * (self.sampled_tokens // 1000)
            )
        else:
            raise CostEstimateUnavailableError(
                f"Unsupported model: {self.model}"
            )

    @property
    def stickys(self) -> List[Message]:
        return [m for m in self._messages if m._sticky]

    def to_dict(self) -> Dict[str, Any]:
        "Exports this thread to a serializable dict."
        return {
            "messages": [dataclasses.asdict(m) for m in self._messages],
            "names": self.names.copy(),
            "api_params": self.api_params,
        }

    def append(self, message: Message) -> None:
        "Adds a new message to the end of this thread"
        if not isinstance(message, Message):
            raise TypeError("append requires a Message object")
        message.name = self.names.get(message.role)
        self._messages.append(message)
        self.dirty = True

    def render(
        self,
        start_index: Optional[int] = None,
        end_index: Optional[int] = None,
        display_indicators: bool = True,
    ) -> str:
        """Renders this thread as a human-readable transcript

        args:
            start_index: the beginning of the range of messages to render
            end_index: the end of the range of messages to render
            display_indicators: Output symbols to indicate particular message
                states (such as an asterisk for sticky messages)
        """
        lines = (
            ("*" if display_indicators and msg._sticky else "")
            + (msg.name if msg.name is not None else msg.role)
            + ": "
            + msg.content
            for msg in self._messages[start_index:end_index]
        )
        return "\n".join(lines)

    def set_api_param(self, key: str, val: Any) -> None:
        "Set an OpenAI API parameter to send with future messages"
        SPECIAL_OPTS = frozenset(("model", "messages", "stream"))
        opts = (
            frozenset(
                inspect.signature(
                    self._openai.chat.completions.create
                ).parameters.keys()
            )
            - SPECIAL_OPTS
        )
        if key not in opts:
            raise APIParameterError(f"Invalid API parameter {key}")
        self._api_params[key] = val
        self.dirty = True

    def _pre_send(self):
        """
        A method called when sending a thread before the actual OpenAI API
        call.
        """
        if self._api_params.get("n", 1) > 1 and self.stream:
            raise NotImplementedError(
                "Streaming multiple completions is not currently supported"
            )

    def _get_openai_kwargs(self) -> Dict[str, Any]:
        """
        Returns the literal keyword arguments passed to
        OpenAI.chat.completions.create.
        """
        return {
            "model": self.model,
            "messages": [
                dataclasses.asdict(
                    m,
                    dict_factory=lambda x: {
                        k: v
                        for k, v in x
                        if not (
                            k.startswith("_") or (k == "name" and v is None)
                        )
                    },
                )
                for m in self._messages
            ],
            "stream": self.stream,
            **self._api_params,
        }

    def send(self) -> Union[Message, MessageStream]:
        """
        Send the current contents of this thread to GPT and append the result
        to this thread.
        """
        self._pre_send()
        resp = self._openai.chat.completions.create(
            **self._get_openai_kwargs()
        )
        return self._post_send(resp, MessageStream)

    async def asend(self) -> Union[Message, AioMessageStream]:
        """
        Asynchronously send the current contents of this thread to GPT and
        append the result to this thread. Note that this method must
        be awaited.
        """
        if self._async_openai is None:
            self._async_openai = openai.AsyncOpenAI()
        self._pre_send()
        resp = await self._openai.chat.completions.create(
            **self._get_openai_kwargs()
        )
        return self._post_send(resp, AioMessageStream)

    S = TypeVar("S", bound=_stream)

    def _post_send(self, resp, stream_cls: Type[S]) -> Union[Message, S]:
        "Handles API response objects generated by openai."
        if not self.stream:
            if resp.model not in (
                "gpt-4-0314",
                "gpt-4-0613",
            ) and resp.model.startswith("gpt-4"):
                self.prompt_tokens = None
                self.sampled_tokens = None
            if self.prompt_tokens is not None:
                self.prompt_tokens += resp.usage.prompt_tokens
            if self.sampled_tokens is not None:
                self.sampled_tokens += resp.usage.completion_tokens
            res = None
            for choice in resp.choices:
                msg = Message(
                    content=choice.message.content,
                    role=choice.message.role,
                )
                self.append(msg)
                if res is None:
                    res = msg  # Return the first choice
            if res is not None:
                return res
            else:
                raise RuntimeError("Empty OpenAI choices!")
        else:
            self.prompt_tokens = None
            self.sampled_tokens = None
            s = stream_cls(resp)
            self.append(s.message)
            return s

    def pop(self, n: Optional[int] = None) -> Message:
        "Remove the nth message from this thread and return it"
        if n is None:
            n = -1
        if self._messages[n]._sticky:
            raise PopStickyMessageError
        res = self._messages.pop(n)
        self.dirty = True
        return res

    def clear(self) -> None:
        "Remove *all* messages (except those marked sticky) from this thread"
        if self._messages:
            self.dirty = True
        self._messages = self.stickys

    def flip(self) -> Message:
        "Move the final message to the beginning of the thread"
        msg = self.pop()
        self._messages.insert(0, msg)
        return msg

    def rename(
        self,
        role: str,
        name: str,
        start_index: Optional[int] = None,
        end_index: Optional[int] = None,
    ):
        """
        Changes the name set on all non-sticky messages of the specified role
        in this thread. If start_index or end_index is specified, only
        messages in the specified range are affected
        """
        for msg in self._messages[start_index:end_index]:
            if msg.role == role and not msg._sticky:
                msg.name = name
                self.dirty = True

    def sticky(
        self, start_index: Optional[int], end_index: Optional[int], state: bool
    ):
        """
        Stickys or unstickys (depending on the state parameter) all messages
        in this thread. If start_index or end_index is specified, only
        messages in the specified range are affected
        """
        for m in self._messages[start_index:end_index]:
            m._sticky = state
            self.dirty = True
