import dataclasses
import inspect
import openai

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    Optional,
    Sequence,
    Tuple,
    Type,
)

from .message import Image, Message, MessageAttachment

"""
This module contains the LLMProvider class and included implementations.
Copyright 2024 Bill Dengler
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""


@dataclasses.dataclass
class LLMResponse:
    message: Message
    prompt_tokens: Optional[int] = None
    sampled_tokens: Optional[int] = None
    cost_in_cents: Optional[int] = None

    def __iter__(self):
        "The default iterator for non-streaming LLMResponse objects."
        yield self.message.content


class InvalidAPIParameterError(Exception):
    pass


class CompletionError(Exception):
    pass


class LLMProvider(ABC):
    """
    An object which generates the most likely next Message
    given a sequence of Messages.
    """

    supports_name = False
    _attachment_formatters: Dict[
        Type[MessageAttachment], Callable[[MessageAttachment], Dict[str, Any]]
    ] = {}

    def __init__(self, model: Optional[str] = None):
        self.model: Optional[str] = model or self.get_best_model()
        self._api_params: Dict[str, Any] = {}
        self.stream: bool = False

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
        return params

    @property
    @abstractmethod
    def valid_models(self) -> Iterable[str]:
        """
        A collection of model names that can be set on this LLM provider
        """
        return ()

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

    def get_best_model(self) -> str:
        """
        For providers that support multiple models, this method returns the
        name of the most capable available option.
        """
        raise NotImplementedError

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
        formatter = self._attachment_formatters.get(type(attachment))
        if formatter:
            return formatter(attachment)
        raise ValueError(
            f"{type(attachment).__name__} attachments aren't supported by"
            " this LLM"
        )


class OpenAI(LLMProvider):
    supports_name = True

    def __init__(self, client, *args, **kwargs):
        self._client = client
        self._models = {m.id for m in self._client.models.list().data}
        super().__init__(*args, **kwargs)
        self.stream = True

    def _message_to_openai(self, msg: Message) -> Dict[str, Any]:
        res = dataclasses.asdict(
            msg,
            dict_factory=lambda x: {
                k: v
                for k, v in x
                if not (k.startswith("_") or (k == "name" and v is None))
            },
        )
        if msg._attachments:
            res["content"] = [
                {"type": "text", "text": msg.content},
                *[self.format_attachment(a) for a in msg._attachments],
            ]
        return res

    @staticmethod
    def _estimate_cost_in_cents(
        model: str, prompt_tokens: int, sampled_tokens: int
    ) -> Optional[Decimal]:
        COST_PER_PROMPT_SAMPLED: Dict[str, Tuple[Decimal, Decimal]] = {
            "gpt-4o-2024-08-06": (
                Decimal("2.5") / Decimal("1000000"),
                Decimal("10") / Decimal("1000000"),
            ),
            "gpt-4o-2024-05-13": (
                Decimal("5") / Decimal("1000000"),
                Decimal("15") / Decimal("1000000"),
            ),
            "gpt-4o-mini-2024-07-18": (
                Decimal("0.15") / Decimal("1000000"),
                Decimal("0.6") / Decimal("1000000"),
            ),
            "gpt-4-turbo-2024-04-09": (
                Decimal("10") / Decimal("1000000"),
                Decimal("30") / Decimal("1000000"),
            ),
            "gpt-4-0125-preview": (
                Decimal("10") / Decimal("1000000"),
                Decimal("30") / Decimal("1000000"),
            ),
            "gpt-4-1106-preview": (
                Decimal("10") / Decimal("1000000"),
                Decimal("30") / Decimal("1000000"),
            ),
            "gpt-4-1106-vision-preview": (
                Decimal("10") / Decimal("1000000"),
                Decimal("30") / Decimal("1000000"),
            ),
            "gpt-4-0613": (
                Decimal("30") / Decimal("1000000"),
                Decimal("60") / Decimal("1000000"),
            ),
            "gpt-3.5-turbo-0125": (
                Decimal("0.5") / Decimal("1000000"),
                Decimal("1.5") / Decimal("1000000"),
            ),
            "gpt-3.5-turbo-1106": (
                Decimal("1") / Decimal("1000000"),
                Decimal("2") / Decimal("1000000"),
            ),
            "gpt-3.5-turbo-0613": (
                Decimal("1.5") / Decimal("1000000"),
                Decimal("2") / Decimal("1000000"),
            ),
            "gpt-3.5-turbo-16k-0613": (
                Decimal("3") / Decimal("1000000"),
                Decimal("4") / Decimal("1000000"),
            ),
            "gpt-3.5-turbo-0301": (
                Decimal("1.5") / Decimal("1000000"),
                Decimal("2") / Decimal("1000000"),
            ),
        }

        if model not in COST_PER_PROMPT_SAMPLED:
            return None
        prompt_scale, sampled_scale = COST_PER_PROMPT_SAMPLED[model]
        return (
            Decimal(prompt_tokens) * prompt_scale
            + Decimal(sampled_tokens) * sampled_scale
        ) * Decimal("100")

    def complete(self, messages: Sequence[Message]) -> LLMResponse:
        kwargs = {
            "model": self.model,
            "messages": [self._message_to_openai(m) for m in messages],
            "stream": self.stream,
            **self.validate_api_params(self.api_params),
        }
        if self.stream:
            # Enable usage statistics
            kwargs["stream_options"] = {"include_usage": True}
        if kwargs["model"] == "gpt-4-vision-preview":
            # For some unknown reason, OpenAI sets a very low
            # default max_tokens. For consistency with other models,
            # set it to the maximum if not overridden by the user.
            kwargs.setdefault("max_tokens", 4096)
        try:
            resp = self._client.chat.completions.create(**kwargs)
        except openai.OpenAIError as e:
            raise CompletionError(e.message) from e
        if isinstance(resp, openai.Stream):
            return StreamedOpenAIResponse(resp, self)
        if len(resp.choices) != 1:
            return None
        choice = resp.choices[0]
        prompt_tokens = resp.usage.prompt_tokens
        sampled_tokens = resp.usage.completion_tokens

        return LLMResponse(
            message=Message(
                content=choice.message.content, role=choice.message.role
            ),
            prompt_tokens=prompt_tokens,
            sampled_tokens=sampled_tokens,
            cost_in_cents=self.__class__._estimate_cost_in_cents(
                model=resp.model,
                prompt_tokens=prompt_tokens,
                sampled_tokens=sampled_tokens,
            ),
        )

    def validate_api_params(self, params):
        SPECIAL_OPTS = frozenset(
            ("model", "messages", "stream", "n", "stream_options")
        )
        valid_opts = (
            frozenset(
                inspect.signature(
                    self._client.chat.completions.create
                ).parameters.keys()
            )
            - SPECIAL_OPTS
        )
        for opt in params:
            if opt not in valid_opts:
                raise InvalidAPIParameterError(f"Unknown parameter {opt}")
        return params

    @property
    def valid_models(self) -> Iterable[str]:
        return self._models

    def get_best_model(self):
        BEST_MODELS = (
            "gpt-4o",
            "gpt-4-turbo",
            "gpt-4o-mini",
            "gpt-4",
            "gpt-3.5-turbo",
        )
        res = next(
            (model for model in BEST_MODELS if model in self.valid_models),
            None,
        )
        if res is None:
            raise RuntimeError("No known GPT model available!")
        else:
            return res


@OpenAI.register_attachment_formatter(Image)
def format_image_for_openai(img: Image) -> Dict[str, Any]:
    res = {"type": "image_url", "image_url": {"url": img.url}}
    if img.detail is not None:
        res["image_url"]["detail"] = img.detail
    return res


class StreamedOpenAIResponse(LLMResponse):
    def __init__(self, backing_stream: openai.Stream, provider: OpenAI):
        self._stream = backing_stream
        self._provider = provider

        m = Message(content="", role="")
        super().__init__(m)

    def __iter__(self):
        return self

    def __next__(self):
        chunk = next(self._stream)
        if chunk.usage:
            prompt_tokens = chunk.usage.prompt_tokens
            sampled_tokens = chunk.usage.completion_tokens
            self.prompt_tokens = prompt_tokens
            self.sampled_tokens = sampled_tokens
            self.cost_in_cents = (
                self._provider.__class__._estimate_cost_in_cents(
                    model=chunk.model,
                    prompt_tokens=prompt_tokens,
                    sampled_tokens=sampled_tokens,
                )
            )
        if len(chunk.choices) != 1:
            return ""
        delta = chunk.choices[0].delta
        if delta.role:
            self.message.role += delta.role
        if delta.content:
            self.message.content += delta.content
            return delta.content
        else:
            return ""
