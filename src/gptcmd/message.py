import base64
import dataclasses
import mimetypes
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any, ClassVar, Dict, Iterable, Optional, List, Tuple, Type

"""
This module contains classes and types for interacting with messages and
message threads.
Copyright 2023 Bill Dengler
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""


class MessageAttachment(ABC):
    """
    A non-text component that can be associated with a Message, such as an
    image for vision models.
    """

    _type_registry: Dict[str, Type["MessageAttachment"]] = {}
    type: ClassVar[str]

    @classmethod
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls._type_registry[cls.type] = cls

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MessageAttachment":
        """
        Instantiate a MessageAttachment from a dict in the format returned by
        MessageAttachment.to_dict()
        """
        attachment_type = d.get("type")
        if attachment_type in cls._type_registry:
            return cls._type_registry[attachment_type]._deserialize(
                d.get("data", {})
            )
        else:
            raise ValueError(f"Unrecognized type: {attachment_type}")

    @classmethod
    @abstractmethod
    def _deserialize(cls, d: Dict[str, Any]) -> "MessageAttachment":
        "Deserialize a dict into a MessageAttachment subclass instance"
        pass

    def to_dict(self) -> Dict[str, Any]:
        "Exports this attachment as a serializable dict"
        return {"type": self.__class__.type, "data": self._serialize()}

    @abstractmethod
    def _serialize(self) -> Dict[str, Any]:
        "Serialize this attachment into a dict"
        pass

    def __eq__(self, other):
        return self.to_dict() == other.to_dict()


class Image(MessageAttachment):
    "An image reachable by URL that can be fetched by the LLM API."

    type = "image_url"

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


@dataclasses.dataclass
class Message:
    """A message sent to or received from an LLM."""

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
    #: A collection of attached objects, such as images
    _attachments: Iterable[MessageAttachment] = dataclasses.field(
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
            if k == "_attachments":
                kwargs[k] = [MessageAttachment.from_dict(i) for i in v]
            elif k in valid_keys:
                kwargs[k] = v
        return cls(**kwargs)

    def to_dict(self) -> Dict[str, Any]:
        "Exports this message as a serializable dict"
        res = {f.name: getattr(self, f.name) for f in dataclasses.fields(self)}
        res["_attachments"] = [a.to_dict() for a in self._attachments]
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
        self.names: Dict[str, str] = names if names is not None else {}
        self.dirty: bool = False

    @classmethod
    def from_dict(cls, d: Dict[str, Any], name: str):
        """
        Instantiate a MessageThread from a dict in the format returned by
        MessageThread.to_dict()
        """
        messages = [Message.from_dict(m) for m in d.get("messages", [])]
        names = d.get("names")
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
        return [m for m in self._messages if m._sticky]

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
            ("*" if display_indicators and msg._sticky else "")
            + ("@" * len(msg._attachments) if display_indicators else "")
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
