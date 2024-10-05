import unittest

from gptcmd.llm import InvalidAPIParameterError, LLMProvider, LLMResponse
from gptcmd.message import Message
from typing import Dict, Sequence


class CactusProvider(LLMProvider):
    @classmethod
    def from_config(cls, conf: Dict):
        return cls(**conf)

    def complete(self, messages: Sequence[Message]) -> LLMResponse:
        return LLMResponse(Message(content="Cactus cactus!", role="assistant"))

    def validate_api_params(self, params):
        if "invalid_param" in params:
            raise InvalidAPIParameterError("Invalid parameter")
        return params

    @property
    def valid_models(self):
        return ["saguaro-1", "saguaro-2"]

    def get_best_model(self):
        return "saguaro-2"


class TestLLMProvider(unittest.TestCase):
    def setUp(self):
        self.llm = CactusProvider()

    def test_init(self):
        self.assertEqual(self.llm.model, "saguaro-2")
        self.assertEqual(self.llm._api_params, {})
        self.assertFalse(self.llm.stream)

    def test_set_api_param_valid(self):
        self.llm.set_api_param("temperature", 0.8)
        self.assertEqual(self.llm._api_params["temperature"], 0.8)

    def test_set_api_param_invalid(self):
        with self.assertRaises(InvalidAPIParameterError):
            self.llm.set_api_param("invalid_param", "value")

    def test_update_api_params_valid(self):
        self.llm.update_api_params({"temperature": 0.8, "max_tokens": 100})
        self.assertEqual(self.llm._api_params["temperature"], 0.8)
        self.assertEqual(self.llm._api_params["max_tokens"], 100)

    def test_update_api_params_invalid(self):
        with self.assertRaises(InvalidAPIParameterError):
            self.llm.update_api_params(
                {"temperature": 0.8, "invalid_param": "value"}
            )

    def test_complete(self):
        messages = [Message(content="Hello", role="user")]
        response = self.llm.complete(messages)
        self.assertIsInstance(response, LLMResponse)
        self.assertEqual(response.message.content, "Cactus cactus!")
        self.assertEqual(response.message.role, "assistant")

    def test_default_text_iter(self):
        messages = [Message(content="Testing testing", role="user")]
        response = self.llm.complete(messages)
        self.assertIsInstance(response, LLMResponse)
        buf = ""
        for chunk in response:
            buf += chunk
        self.assertEqual(buf, "Cactus cactus!")

    def test_valid_models(self):
        self.assertEqual(self.llm.valid_models, ["saguaro-1", "saguaro-2"])

    def test_get_best_model(self):
        self.assertEqual(self.llm.get_best_model(), "saguaro-2")


if __name__ == "__main__":
    unittest.main()
