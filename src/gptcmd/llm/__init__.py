"""
This module contains the LLMProvider class and supporting infrastructure.
Copyright 2024 Bill Dengler
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""

import dataclasses
from abc import ABC, abstractmethod
from decimal import Decimal
from enum import Flag, auto
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    Optional,
    Sequence,
    Type,
    Union,
)

from ..message import Message, MessageAttachment, UnknownAttachment


@dataclasses.dataclass
class LLMResponse:
    message: Message
    prompt_tokens: Optional[int] = None
    sampled_tokens: Optional[int] = None
    cost_in_cents: Optional[Union[int, Decimal]] = None

    def __iter__(self):
        """The default iterator for non-streaming LLMResponse objects."""
        yield self.message.content


class InvalidAPIParameterError(Exception):
    pass


class CompletionError(Exception):
    pass


class LLMProviderFeature(Flag):
    """
    An enum representing optional features that an LLMProvider might
    implement.
    """

    # Whether this LLM implements support for the name attribute
    # on Message objects. If this flag is not set, message names are likely
    # to be ignored.
    MESSAGE_NAME_FIELD = auto()

    # Whether this LLM implements support for streamed responses
    RESPONSE_STREAMING = auto()


class LLMProvider(ABC):
    """
    An object which generates the most likely next Message
    given a sequence of Messages.
    """

    SUPPORTED_FEATURES: LLMProviderFeature = LLMProviderFeature(0)

    def __init__(self, model: Optional[str] = None):
        self.model: Optional[str] = model or self.get_best_model()
        self._api_params: Dict[str, Any] = {}
        self._stream: bool = False

    def __init_subclass__(cls):
        cls._attachment_formatters: Dict[
            Type[MessageAttachment],
            Callable[[MessageAttachment], Dict[str, Any]],
        ] = {}

    @abstractmethod
    def complete(self, messages: Sequence[Message]) -> LLMResponse:
        pass

    @abstractmethod
    def validate_api_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Given a dict of API parameters, this method:
        Raises InvalidAPIParameterError if this model doesn't support a
        parameter defined in the dictionary.
        If the user-provided value is out of range or in the incorrect format,
        this method adjusts the value accordingly.
        """
        pass

    @property
    @abstractmethod
    def valid_models(self) -> Optional[Iterable[str]]:
        """
        A collection of model names that can be set on this LLM provider
        """
        pass

    @classmethod
    @abstractmethod
    def from_config(cls, conf: Dict):
        "Instantiate this object from a dict of configuration file parameters."
        pass

    @property
    def stream(self) -> bool:
        return (
            self._stream
            and LLMProviderFeature.RESPONSE_STREAMING
            in self.SUPPORTED_FEATURES
        )

    @stream.setter
    def stream(self, val: bool):
        if (
            LLMProviderFeature.RESPONSE_STREAMING
            not in self.SUPPORTED_FEATURES
        ):
            raise NotImplementedError(
                "Response streaming is not supported by this LLM"
            )
        self._stream = val

    @property
    def api_params(self) -> Dict[str, Any]:
        return self._api_params.copy()

    def set_api_param(self, key: str, value: Any) -> Any:
        """Set an API parameter after validating it."""
        new_params = self._api_params.copy()
        new_params[key] = value
        validated_params = self.validate_api_params(new_params)
        self._api_params = validated_params
        return validated_params.get(key)

    def unset_api_param(self, key: Optional[str] = None) -> None:
        if key is None:
            self._api_params = {}
        else:
            try:
                del self._api_params[key]
            except KeyError:
                raise InvalidAPIParameterError(f"{key} not set")

    def update_api_params(self, params: Dict[str, Any]) -> None:
        """Update multiple API parameters at once after validating them."""
        new_params = self._api_params.copy()
        new_params.update(params)
        validated_params = self.validate_api_params(new_params)
        self._api_params = validated_params

    @abstractmethod
    def get_best_model(self) -> str:
        """
        This method returns the name of the most capable model offered by
        this provider.
        """
        pass

    @classmethod
    def register_attachment_formatter(
        cls, attachment_type: Type[MessageAttachment]
    ):
        def decorator(func: Callable[[MessageAttachment], Dict[str, Any]]):
            cls._attachment_formatters[attachment_type] = func
            return func

        return decorator

    def format_attachment(
        self, attachment: MessageAttachment
    ) -> Dict[str, Any]:
        if isinstance(attachment, UnknownAttachment):
            raise ValueError(
                f"{attachment.type} attachments are not supported. Perhaps you"
                " need to update Gptcmd or install a package?"
            )
        for cls in self.__class__.__mro__:
            formatter = getattr(cls, "_attachment_formatters", {}).get(
                type(attachment)
            )
            if formatter:
                return formatter(attachment)
        raise ValueError(
            f"{type(attachment).__name__} attachments aren't supported by"
            " this LLM"
        )
