"""
This module contains implementations of LLMProvider for OpenAI and Azure.
Copyright 2024 Bill Dengler
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""

import inspect
import mimetypes
import re

from collections import namedtuple
from decimal import Decimal
from typing import Any, Dict, Iterable, Optional, Sequence

from . import (
    CompletionError,
    InvalidAPIParameterError,
    LLMProviderFeature,
    LLMProvider,
    LLMResponse,
)
from ..message import Audio, Image, Message, MessageRole

import openai

ModelCostInfo = namedtuple(
    "ModelCostInfo", ("prompt_scale", "sampled_scale", "cache_discount_factor")
)


class OpenAI(LLMProvider):
    SUPPORTED_FEATURES = (
        LLMProviderFeature.MESSAGE_NAME_FIELD
        | LLMProviderFeature.RESPONSE_STREAMING
    )

    _reasoning_model_expr = re.compile(r"^o\d.*$")

    def __init__(self, client, *args, **kwargs):
        self._client = client
        try:
            self._models = {m.id for m in self._client.models.list().data}
        except openai.NotFoundError:
            # Some OpenAI-like APIs implement a chat completions endpoint but
            # don't offer a list of models.
            # For these APIs, disable model validation.
            self._models = None
        super().__init__(*args, **kwargs)
        self._stream = True

    @classmethod
    def from_config(cls, conf: Dict):
        SPECIAL_OPTS = (
            "model",
            "provider",
        )
        model = conf.get("model")
        client_opts = {k: v for k, v in conf.items() if k not in SPECIAL_OPTS}
        try:
            client = openai.OpenAI(**client_opts)
        except openai.OpenAIError as e:
            # Import late to avoid circular import
            from ..config import ConfigError

            raise ConfigError(str(e)) from e
        return cls(client, model=model)

    def _message_to_openai(self, msg: Message) -> Dict[str, Any]:
        res = {
            "role": (
                "developer"
                if self.__class__._reasoning_model_expr.match(self.model)
                and msg.role == MessageRole.SYSTEM
                else msg.role
            )
        }
        if msg.name:
            res["name"] = msg.name
        if msg.attachments:
            res["content"] = [
                {"type": "text", "text": msg.content},
                *[self.format_attachment(a) for a in msg.attachments],
            ]
        else:
            res["content"] = msg.content
        return res

    @staticmethod
    def _estimate_cost_in_cents(
        model: str,
        prompt_tokens: int,
        cached_prompt_tokens: int,
        sampled_tokens: int,
    ) -> Optional[Decimal]:
        COST_PER_PROMPT_SAMPLED: Dict[str, ModelCostInfo] = {
            "o3-2025-04-16": ModelCostInfo(
                Decimal("2") / Decimal("1000000"),
                Decimal("8") / Decimal("1000000"),
                Decimal("0.25"),
            ),
            "o1-2024-12-17": ModelCostInfo(
                Decimal("15") / Decimal("1000000"),
                Decimal("60") / Decimal("1000000"),
                Decimal("0.5"),
            ),
            "o1-preview-2024-09-12": ModelCostInfo(
                Decimal("15") / Decimal("1000000"),
                Decimal("60") / Decimal("1000000"),
                Decimal("0.5"),
            ),
            "o4-mini-2025-04-16": ModelCostInfo(
                Decimal("1.1") / Decimal("1000000"),
                Decimal("4.4") / Decimal("1000000"),
                Decimal("0.25"),
            ),
            "o3-mini-2025-01-31": ModelCostInfo(
                Decimal("1.1") / Decimal("1000000"),
                Decimal("4.4") / Decimal("1000000"),
                Decimal("0.5"),
            ),
            "o1-mini-2024-09-12": ModelCostInfo(
                Decimal("3") / Decimal("1000000"),
                Decimal("12") / Decimal("1000000"),
                Decimal("0.5"),
            ),
            "gpt-4.1-2025-04-14": ModelCostInfo(
                Decimal("2") / Decimal("1000000"),
                Decimal("8") / Decimal("1000000"),
                Decimal("0.25"),
            ),
            "gpt-4.5-preview-2025-02-27": ModelCostInfo(
                Decimal("75") / Decimal("1000000"),
                Decimal("150") / Decimal("1000000"),
                Decimal("0.5"),
            ),
            "gpt-4o-audio-preview-2025-06-03": ModelCostInfo(
                Decimal("2.5") / Decimal("1000000"),
                Decimal("10") / Decimal("1000000"),
                Decimal("0.5"),
            ),
            "gpt-4o-audio-preview-2024-12-17": ModelCostInfo(
                Decimal("2.5") / Decimal("1000000"),
                Decimal("10") / Decimal("1000000"),
                Decimal("0.5"),
            ),
            "gpt-4o-2024-11-20": ModelCostInfo(
                Decimal("2.5") / Decimal("1000000"),
                Decimal("10") / Decimal("1000000"),
                Decimal("0.5"),
            ),
            "gpt-4o-2024-08-06": ModelCostInfo(
                Decimal("2.5") / Decimal("1000000"),
                Decimal("10") / Decimal("1000000"),
                Decimal("0.5"),
            ),
            "gpt-4o-2024-05-13": ModelCostInfo(
                Decimal("5") / Decimal("1000000"),
                Decimal("15") / Decimal("1000000"),
                Decimal("0.5"),
            ),
            "gpt-4.1-mini-2025-04-14": ModelCostInfo(
                Decimal("0.4") / Decimal("1000000"),
                Decimal("1.6") / Decimal("1000000"),
                Decimal("0.25"),
            ),
            "gpt-4.1-nano-2025-04-14": ModelCostInfo(
                Decimal("0.1") / Decimal("1000000"),
                Decimal("0.4") / Decimal("1000000"),
                Decimal("0.25"),
            ),
            "gpt-4o-mini-2024-07-18": ModelCostInfo(
                Decimal("0.15") / Decimal("1000000"),
                Decimal("0.6") / Decimal("1000000"),
                Decimal("0.5"),
            ),
            "gpt-4-turbo-2024-04-09": ModelCostInfo(
                Decimal("10") / Decimal("1000000"),
                Decimal("30") / Decimal("1000000"),
                Decimal("0.5"),
            ),
            "gpt-4-0125-preview": ModelCostInfo(
                Decimal("10") / Decimal("1000000"),
                Decimal("30") / Decimal("1000000"),
                Decimal("0.5"),
            ),
            "gpt-4-1106-preview": ModelCostInfo(
                Decimal("10") / Decimal("1000000"),
                Decimal("30") / Decimal("1000000"),
                Decimal("0.5"),
            ),
            "gpt-4-1106-vision-preview": ModelCostInfo(
                Decimal("10") / Decimal("1000000"),
                Decimal("30") / Decimal("1000000"),
                Decimal("0.5"),
            ),
            "gpt-4-0613": ModelCostInfo(
                Decimal("30") / Decimal("1000000"),
                Decimal("60") / Decimal("1000000"),
                Decimal("0.5"),
            ),
            "gpt-3.5-turbo-0125": ModelCostInfo(
                Decimal("0.5") / Decimal("1000000"),
                Decimal("1.5") / Decimal("1000000"),
                Decimal("0.5"),
            ),
            "gpt-3.5-turbo-1106": ModelCostInfo(
                Decimal("1") / Decimal("1000000"),
                Decimal("2") / Decimal("1000000"),
                Decimal("0.5"),
            ),
            "gpt-3.5-turbo-0613": ModelCostInfo(
                Decimal("1.5") / Decimal("1000000"),
                Decimal("2") / Decimal("1000000"),
                Decimal("0.5"),
            ),
            "gpt-3.5-turbo-16k-0613": ModelCostInfo(
                Decimal("3") / Decimal("1000000"),
                Decimal("4") / Decimal("1000000"),
                Decimal("0.5"),
            ),
            "gpt-3.5-turbo-0301": ModelCostInfo(
                Decimal("1.5") / Decimal("1000000"),
                Decimal("2") / Decimal("1000000"),
                Decimal("0.5"),
            ),
        }

        if model not in COST_PER_PROMPT_SAMPLED:
            return None
        info = COST_PER_PROMPT_SAMPLED[model]
        cached_prompt_scale = info.prompt_scale * info.cache_discount_factor
        uncached_prompt_tokens = prompt_tokens - cached_prompt_tokens
        return (
            Decimal(uncached_prompt_tokens) * info.prompt_scale
            + Decimal(cached_prompt_tokens) * cached_prompt_scale
            + Decimal(sampled_tokens) * info.sampled_scale
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
            raise CompletionError(str(e)) from e
        if isinstance(resp, openai.Stream):
            return StreamedOpenAIResponse(resp, self)
        if resp.choices is None:
            raise CompletionError("Empty response (no choices specified)")
        elif len(resp.choices) != 1:
            raise CompletionError(
                f"Unexpected number of choices ({len(resp.choices)}) from"
                " OpenAI response"
            )
        choice = resp.choices[0]
        prompt_tokens = resp.usage.prompt_tokens
        prompt_tokens_details = getattr(
            resp.usage, "prompt_tokens_details", None
        )
        if prompt_tokens_details is None:
            cached_prompt_tokens = 0
        else:
            cached_prompt_tokens = prompt_tokens_details.cached_tokens
        sampled_tokens = resp.usage.completion_tokens

        return LLMResponse(
            message=Message(
                content=choice.message.content,
                role=MessageRole(choice.message.role),
            ),
            prompt_tokens=prompt_tokens,
            sampled_tokens=sampled_tokens,
            cost_in_cents=self.__class__._estimate_cost_in_cents(
                model=resp.model,
                prompt_tokens=prompt_tokens,
                cached_prompt_tokens=cached_prompt_tokens,
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
    def stream(self) -> bool:
        return self._stream

    @stream.setter
    def stream(self, val: bool):
        self._stream = val

    @property
    def valid_models(self) -> Iterable[str]:
        return self._models

    def get_best_model(self):
        BEST_MODELS = (
            "gpt-4.1",
            "gpt-4o",
            "gpt-4-turbo",
            "gpt-4.1-mini",
            "gpt-4o-mini",
            "gpt-4",
            "gpt-3.5-turbo",
        )
        res = next(
            (model for model in BEST_MODELS if model in self.valid_models),
            None,
        )
        if res is None:
            raise RuntimeError(
                "No known GPT model available! If this is an OpenAI-like API, "
                "set the model explicitly"
            )
        else:
            return res


class AzureAI(OpenAI):
    AZURE_API_VERSION = "2024-06-01"

    @classmethod
    def from_config(cls, conf):
        SPECIAL_OPTS = (
            "model",
            "provider",
            "api_version",
        )
        model = conf.get("model")
        client_opts = {k: v for k, v in conf.items() if k not in SPECIAL_OPTS}
        client_opts["api_version"] = cls.AZURE_API_VERSION
        endpoint = client_opts.pop("endpoint", None)
        if endpoint:
            client_opts["azure_endpoint"] = endpoint
        client = openai.AzureOpenAI(**client_opts)
        return cls(client, model=model)


@OpenAI.register_attachment_formatter(Image)
def format_image_for_openai(img: Image) -> Dict[str, Any]:
    res = {"type": "image_url", "image_url": {"url": img.url}}
    if img.detail is not None:
        res["image_url"]["detail"] = img.detail
    return res


@OpenAI.register_attachment_formatter(Audio)
def format_audio_for_openai(a: Audio) -> Dict[str, Any]:
    res: Dict[str, Any] = {
        "type": "input_audio",
        "input_audio": {"data": a.b64},
    }
    ext = mimetypes.guess_extension(a.mimetype)
    if ext:
        res["input_audio"]["format"] = ext.lstrip(".")
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
        try:
            chunk = next(self._stream)
        except openai.OpenAIError as e:
            raise CompletionError(str(e)) from e
        if chunk is None:
            return ""
        if chunk.usage:
            prompt_tokens = chunk.usage.prompt_tokens
            prompt_tokens_details = getattr(
                chunk.usage, "prompt_tokens_details", None
            )
            if prompt_tokens_details is None:
                cached_prompt_tokens = 0
            else:
                cached_prompt_tokens = prompt_tokens_details.cached_tokens
            sampled_tokens = chunk.usage.completion_tokens
            self.prompt_tokens = prompt_tokens
            self.sampled_tokens = sampled_tokens
            self.cost_in_cents = (
                self._provider.__class__._estimate_cost_in_cents(
                    model=chunk.model,
                    prompt_tokens=prompt_tokens,
                    cached_prompt_tokens=cached_prompt_tokens,
                    sampled_tokens=sampled_tokens,
                )
            )
        if chunk.choices is None or len(chunk.choices) != 1:
            return ""
        delta = chunk.choices[0].delta
        if delta is None:
            return ""
        if delta.role and delta.role != self.message.role:
            self.message.role += delta.role
        if delta.content:
            self.message.content += delta.content
            return delta.content
        else:
            return ""
