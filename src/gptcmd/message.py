"""
This module contains classes and types for interacting with messages and
message threads.
Copyright 2024 Bill Dengler
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""


import base64
import dataclasses
import mimetypes
import sys
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import (
    Any,
    Callable,
    Dict,
    Generic,
    Iterable,
    List,
    Optional,
    Tuple,
    Type,
    TypeVar,
)

if sys.version_info >= (3, 11):
    from enum import StrEnum
elif sys.version_info >= (3, 8, 6):
    from backports.strenum import StrEnum
else:
    from strenum import StrEnum


T = TypeVar("T")


class TwoWayRegistrar(Generic[T]):
    """
    A registrar that maintains both forward and reverse mappings between keys
    and classes.
    Ensures a one-to-one relationship and provides reverse lookup.
    """

    def __init__(self):
        self._registry: Dict[str, Type[T]] = {}
        self._reverse_registry: Dict[Type[T], str] = {}

    def __contains__(self, key: str) -> bool:
        return key in self._registry

    def register(self, key: str) -> Callable[[Type[T]], Type[T]]:
        """
        Decorator to register a class with the passed-in key.
        """

        def decorator(cls: Type[T]) -> Type[T]:
            if key in self._registry:
                raise ValueError(f"{key} is already registered")
            elif cls in self._reverse_registry:
                raise ValueError(f"{cls} is already registered")
            self._registry[key] = cls
            self._reverse_registry[cls] = key
            return cls

        return decorator

    def get(self, key: str) -> Type[T]:
        """
        Retrieve a class from the registry by key.
        """
        if key not in self._registry:
            raise KeyError(f"{key} is not registered")
        return self._registry[key]

    def reverse_get(self, cls: Type[T]) -> str:
        """
        Retrieve the key associated with a class from the reverse registry.
        """
        if cls not in self._reverse_registry:
            raise KeyError(f"Class '{cls.__name__}' is not registered")
        return self._reverse_registry[cls]


attachment_type_registrar: TwoWayRegistrar["MessageAttachment"] = (
    TwoWayRegistrar()
)


class MessageAttachment(ABC):
    """
    A non-text component that can be associated with a Message, such as an
    image for vision models.
    """

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MessageAttachment":
        """
        Instantiate a MessageAttachment from a dict in the format returned by
        MessageAttachment.to_dict()
        """
        attachment_type_key = d.get("type")
        attachment_data = d.get("data", {})
        try:
            attachment_type = attachment_type_registrar.get(
                attachment_type_key
            )
        except KeyError:
            return UnknownAttachment(
                _type=attachment_type_key, _data=attachment_data
            )
        return attachment_type._deserialize(attachment_data)

    @classmethod
    @abstractmethod
    def _deserialize(cls, d: Dict[str, Any]) -> "MessageAttachment":
        "Deserialize a dict into a MessageAttachment subclass instance"
        pass

    def to_dict(self) -> Dict[str, Any]:
        "Exports this attachment as a serializable dict"
        return {
            "type": attachment_type_registrar.reverse_get(self.__class__),
            "data": self._serialize(),
        }

    @abstractmethod
    def _serialize(self) -> Dict[str, Any]:
        "Serialize this attachment into a dict"
        pass

    def __eq__(self, other):
        return self.to_dict() == other.to_dict()


@attachment_type_registrar.register("image_url")
class Image(MessageAttachment):
    "An image reachable by URL that can be fetched by the LLM API."

    def __init__(self, url: str, detail: Optional[str] = None):
        self.url = url
        self.detail = detail

    @classmethod
    def from_path(cls, path: str, *args, **kwargs):
        "Instantiate an Image from a file"
        with open(path, "rb") as fin:
            b64data = base64.b64encode(fin.read()).decode("utf-8")
        mimetype = mimetypes.guess_type(path)[0]
        return cls(url=f"data:{mimetype};base64,{b64data}", *args, **kwargs)

    @classmethod
    def _deserialize(cls, d: Dict[str, Any]) -> "Image":
        return cls(url=d["url"], detail=d.get("detail"))

    def _serialize(self) -> Dict[str, Any]:
        res = {"url": self.url}
        if self.detail is not None:
            res["detail"] = self.detail
        return res


class UnknownAttachment(MessageAttachment):
    """
    A MessageAttachment created when a dict in the form returned by
    MessageAttachment.to_dict contains an unknown or ambiguous type.
    This class should not be instantiated directly.
    """

    def __init__(self, _type: str, _data: Dict):
        self.data = _data
        self.type = _type

    @classmethod
    def _deserialize(cls, data):
        return cls(_type=None, _data=data)

    def _serialize(self):
        return self.data.copy()

    def to_dict(self):
        # Since these attachments are explicitly not registered, use our
        # internal type field instead of the registrar.
        return {"type": self.type, "data": self._serialize()}


class MessageRole(StrEnum):
    """
    An enumeration defining valid values for the role attribute on
    Message objects
    """

    # Don't use enum.auto() to define member values since its behaviour
    # differs between strenum and enum.
    # When gptcmd no longer supports Python 3.7, we can migrate to the
    # backports.strenum package.

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclasses.dataclass
class Message:
    """A message sent to or received from an LLM."""

    #: The text content of the message
    content: str
    #: a member of MessageRole that defines the conversational role of the
    #: author of this message
    role: MessageRole
    #: The name of the author of this message
    name: Optional[str] = None
    #: Whether this message is "sticky" (not affected by thread-level deletion
    #: operations)
    sticky: bool = False
    #: A collection of attached objects, such as images
    attachments: List[MessageAttachment] = dataclasses.field(
        default_factory=list
    )

    @classmethod
    def from_dict(cls, d: Dict[str, Any]):
        """
        Instantiate a Message from a dict in the format returned by
        Message.to_dict()
        """
        valid_keys = [f.name for f in dataclasses.fields(cls)]
        kwargs = {}
        for k, v in d.items():
            if k == "attachments":
                kwargs[k] = [MessageAttachment.from_dict(i) for i in v]
            elif k == "role":
                kwargs[k] = MessageRole(v)
            elif k == "_sticky":  # v1 sticky field
                kwargs["sticky"] = v
            elif k in valid_keys:
                kwargs[k] = v
        return cls(**kwargs)

    def to_dict(self) -> Dict[str, Any]:
        "Exports this message as a serializable dict"
        res = {f.name: getattr(self, f.name) for f in dataclasses.fields(self)}
        res["attachments"] = [a.to_dict() for a in self.attachments]
        return res


class PopStickyMessageError(Exception):
    "Thrown when attempting to pop a Message marked sticky"

    pass


class MessageThread(Sequence):
    def __init__(
        self,
        name: str,
        messages: Optional[Iterable[Message]] = None,
        names: Optional[Dict[str, str]] = None,
    ):
        """A conversation thread

        args:
            name: The display name of this thread
            messages: An iterable of Message objects from which to populate
                this thread
            names: Mapping of roles to names that should be set on
                future messages added to this thread
        """
        self.name: str = name
        self._messages: List[Message] = (
            [dataclasses.replace(m) for m in messages]
            if messages is not None
            else []
        )
        self.names: Dict[MessageRole, str] = names if names is not None else {}
        self.dirty: bool = False

    @classmethod
    def from_dict(cls, d: Dict[str, Any], name: str):
        """
        Instantiate a MessageThread from a dict in the format returned by
        MessageThread.to_dict()
        """
        messages = [Message.from_dict(m) for m in d.get("messages", [])]
        names = d.get("names")
        if names:
            names = {MessageRole(k): v for k, v in names.items()}
        res = cls(name=name, messages=messages, names=names)
        return res

    def __repr__(self) -> str:
        return f"<{self.name} MessageThread {self._messages!r}>"

    def __getitem__(self, n):
        return self._messages[n]

    def __len__(self) -> int:
        return len(self._messages)

    @property
    def messages(self) -> Tuple[Message, ...]:
        return tuple(self._messages)

    @messages.setter
    def messages(self, val: Iterable[Message]):
        self._messages = list(val)
        self.dirty = True

    @property
    def stickys(self) -> List[Message]:
        return [m for m in self._messages if m.sticky]

    def to_dict(self) -> Dict[str, Any]:
        "Exports this thread to a serializable dict."
        return {
            "messages": [m.to_dict() for m in self._messages],
            "names": self.names.copy(),
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
            ("*" if display_indicators and msg.sticky else "")
            + ("@" * len(msg.attachments) if display_indicators else "")
            + (msg.name if msg.name is not None else msg.role)
            + ": "
            + msg.content
            for msg in self._messages[start_index:end_index]
        )
        return "\n".join(lines)

    def pop(self, n: Optional[int] = None) -> Message:
        "Remove the nth message from this thread and return it"
        if n is None:
            n = -1
        if self._messages[n].sticky:
            raise PopStickyMessageError
        res = self._messages.pop(n)
        self.dirty = True
        return res

    def clear(self) -> None:
        "Remove *all* messages (except those marked sticky) from this thread"
        if self._messages:
            self.dirty = True
        self._messages = self.stickys

    def move(self, i: Optional[int], j: Optional[int]) -> Message:
        """Pop the message at index i and re-insert it at index j"""
        msg = self.pop(i)
        if j is None:
            j = len(self)
        self._messages.insert(j, msg)
        return msg

    def rename(
        self,
        role: MessageRole,
        name: str,
        start_index: Optional[int] = None,
        end_index: Optional[int] = None,
    ) -> List[Message]:
        """
        Changes the name set on all non-sticky messages of the specified role
        in this thread. If start_index or end_index is specified, only
        messages in the specified range are affected
        """
        res = []
        for msg in self._messages[start_index:end_index]:
            if msg.role == role and not msg.sticky:
                msg.name = name
                res.append(msg)
        if res:
            self.dirty = True
        return res

    def sticky(
        self, start_index: Optional[int], end_index: Optional[int], state: bool
    ) -> List[Message]:
        """
        Stickys or unstickys (depending on the state parameter) all messages
        in this thread. If start_index or end_index is specified, only
        messages in the specified range are affected. Returns a list of
        messages affected by this operation.
        """
        res = []
        for m in self._messages[start_index:end_index]:
            if m.sticky != state:
                m.sticky = state
                res.append(m)
        if res:
            self.dirty = True
        return res
