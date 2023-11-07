import unittest
from gptcmd import APIParameterError, MessageThread, Message

"""
This module contains unit tests for MessageThread and related objects.
Copyright 2023 Bill Dengler
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""


class TestMessageThread(unittest.TestCase):
    def setUp(self):
        self.thread = MessageThread(name="test")

    def test_append(self):
        self.thread.append(Message(content="Hello", role="user"))
        self.assertEqual(len(self.thread), 1)
        self.assertEqual(self.thread[0].content, "Hello")
        self.assertEqual(self.thread[0].role, "user")

    def test_render(self):
        self.thread.append(Message(content="What is a cactus?", role="user"))
        self.thread.append(
            Message(
                content=(
                    "A desert plant with thick, fleshy stems, sharp spines,"
                    " and beautiful, short-lived flowers."
                ),
                role="assistant",
            )
        )
        self.assertEqual(
            self.thread.render(),
            "user: What is a cactus?\nassistant: A desert plant with"
            " thick, fleshy stems, sharp spines, and beautiful,"
            " short-lived flowers.",
        )

    def test_render_custom_names(self):
        self.thread.names = {"user": "Bill", "assistant": "Kevin"}
        self.thread.append(Message(content="What is a cactus?", role="user"))
        self.thread.append(
            Message(
                content=(
                    "A desert plant with thick, fleshy stems, sharp spines,"
                    " and beautiful, short-lived flowers."
                ),
                role="assistant",
            )
        )
        self.assertEqual(
            self.thread.render(),
            "Bill: What is a cactus?\nKevin: A desert plant with thick,"
            " fleshy stems, sharp spines, and beautiful, short-lived"
            " flowers.",
        )

    def test_set_api_param(self):
        self.thread.set_api_param("temperature", 0.8)
        self.assertEqual(self.thread.api_params["temperature"], 0.8)

    def test_set_api_param_special(self):
        with self.assertRaises(APIParameterError):
            self.thread.set_api_param(
                "messages", [{"content": "fail!", "role": "user"}]
            )
        self.assertNotIn("messages", self.thread._api_params)

    def test_set_api_param_invalid(self):
        with self.assertRaises(APIParameterError):
            self.thread.set_api_param("frequency_pen", 1.5)
        self.assertNotIn("frequency_pen", self.thread._api_params)

    def test_pop(self):
        self.thread.append(Message(content="Hello", role="user"))
        self.thread.append(Message(content="Hi", role="assistant"))
        popped = self.thread.pop()
        self.assertEqual(len(self.thread), 1)
        self.assertEqual(popped.content, "Hi")
        self.assertEqual(popped.role, "assistant")
        self.thread.pop()
        with self.assertRaises(IndexError):
            self.thread.pop()

    def test_clear(self):
        self.thread.append(Message(content="Hello", role="user"))
        self.thread.append(Message(content="Hi", role="assistant"))
        self.thread.clear()
        self.assertEqual(len(self.thread), 0)

    def test_clear_sticky(self):
        self.thread.append(Message(content="Hello", role="user", _sticky=True))
        self.thread.append(Message(content="Hi", role="assistant"))
        self.thread.clear()
        self.assertEqual(len(self.thread), 1)

    def test_clear_sticky_unsticky(self):
        self.thread.append(Message(content="Hello", role="user"))
        self.thread.append(Message(content="Hi", role="assistant"))
        self.thread.sticky(0, 1, True)
        self.thread.clear()
        self.assertEqual(len(self.thread), 1)
        self.thread.sticky(None, None, False)
        self.thread.clear()
        self.assertEqual(len(self.thread), 0)

    def test_flip(self):
        self.thread.append(Message(content="Hello", role="user"))
        self.thread.append(Message(content="Hi", role="assistant"))
        self.thread.flip()
        self.assertEqual(self.thread[0].content, "Hi")
        self.assertEqual(self.thread[0].role, "assistant")
        self.assertEqual(self.thread[1].content, "Hello")
        self.assertEqual(self.thread[1].role, "user")

    def test_rename(self):
        self.thread.append(Message(content="Hello", role="user"))
        self.thread.append(Message(content="Hi", role="assistant"))
        self.thread.rename(role="assistant", name="GPT")
        self.assertEqual(self.thread[1].name, "GPT")

    def test_rename_limited_range(self):
        self.thread.append(Message(content="abc", role="user"))
        self.thread.append(Message(content="def", role="assistant"))
        self.thread.append(Message(content="ghi", role="user"))
        self.thread.append(Message(content="jkl", role="user"))
        self.thread.rename(
            role="user", name="Kevin", start_index=0, end_index=2
        )
        self.assertEqual(self.thread[0].name, "Kevin")
        self.assertIsNone(self.thread[1].name)
        self.assertIsNone(self.thread[2].name)
        self.assertIsNone(self.thread[3].name)


if __name__ == "__main__":
    unittest.main()
