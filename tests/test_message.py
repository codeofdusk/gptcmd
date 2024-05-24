import unittest
from gptcmd import MessageThread, Message, PopStickyMessageError
from gptcmd.message import Image

"""
This module contains unit tests for MessageThread and related objects.
Copyright 2023 Bill Dengler
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""


class TestMessageThreadInit(unittest.TestCase):
    def test_init_empty(self):
        thread = MessageThread(name="test")
        self.assertEqual(thread.name, "test")
        self.assertEqual(len(thread), 0)
        self.assertEqual(thread.dirty, False)

    def test_init_with_messages(self):
        messages = [
            Message(content="Hello", role="user"),
            Message(content="Hi", role="assistant"),
        ]
        thread = MessageThread(name="test", messages=messages)
        self.assertEqual(len(thread), 2)
        self.assertEqual(thread[0].content, "Hello")
        self.assertEqual(thread[1].content, "Hi")

    def test_init_with_names(self):
        names = {"user": "Alice", "assistant": "Mila"}
        thread = MessageThread(name="test", names=names)
        self.assertEqual(thread.names, names)


class TestMessageThread(unittest.TestCase):
    def setUp(self):
        self.thread = MessageThread(name="test")

    def test_append(self):
        self.thread.append(Message(content="Hello", role="user"))
        self.assertEqual(len(self.thread), 1)
        self.assertEqual(self.thread[0].content, "Hello")
        self.assertEqual(self.thread[0].role, "user")
        self.assertTrue(self.thread.dirty)

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
            "user: What is a cactus?\nassistant: A desert plant with thick,"
            " fleshy stems, sharp spines, and beautiful, short-lived flowers.",
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
            "Bill: What is a cactus?\nKevin: A desert plant with thick, fleshy"
            " stems, sharp spines, and beautiful, short-lived flowers.",
        )

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

    def test_pop_sticky(self):
        self.thread.append(Message(content="Hello", role="user", _sticky=True))
        with self.assertRaises(PopStickyMessageError):
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

    def test_flip(self):
        self.thread.append(Message(content="Hello", role="user"))
        self.thread.append(Message(content="Hi", role="assistant"))
        flipped = self.thread.flip()
        self.assertEqual(flipped.content, "Hi")
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

    def test_sticky(self):
        self.thread.append(Message(content="Hello", role="user"))
        self.thread.append(Message(content="Hi", role="assistant"))
        self.thread.sticky(0, 1, True)
        self.assertTrue(self.thread[0]._sticky)
        self.assertFalse(self.thread[1]._sticky)

    def test_messages_property(self):
        self.thread.append(Message(content="Hello", role="user"))
        self.thread.append(Message(content="Hi", role="assistant"))
        messages = self.thread.messages
        self.assertIsInstance(messages, tuple)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].content, "Hello")
        self.assertEqual(messages[1].content, "Hi")

    def test_to_dict(self):
        self.thread.append(Message(content="Hello", role="user"))
        self.thread.append(Message(content="Hi", role="assistant"))
        thread_dict = self.thread.to_dict()
        self.assertIn("messages", thread_dict)
        self.assertIn("names", thread_dict)
        self.assertEqual(len(thread_dict["messages"]), 2)

    def test_from_dict(self):
        thread_dict = {
            "messages": [
                {"content": "Hello", "role": "user"},
                {"content": "Hi", "role": "assistant"},
            ],
            "names": {"user": "Alice", "assistant": "Mila"},
        }
        thread = MessageThread.from_dict(thread_dict, name="test")
        self.assertEqual(thread.name, "test")
        self.assertEqual(len(thread), 2)
        self.assertEqual(thread[0].content, "Hello")
        self.assertEqual(thread[1].content, "Hi")
        self.assertEqual(thread.names, {"user": "Alice", "assistant": "Mila"})


class TestMessage(unittest.TestCase):
    def test_message_creation(self):
        message = Message(content="Hello", role="user")
        self.assertEqual(message.content, "Hello")
        self.assertEqual(message.role, "user")
        self.assertIsNone(message.name)
        self.assertFalse(message._sticky)
        self.assertEqual(message._attachments, [])

    def test_message_with_attachment(self):
        image = Image(url="http://example.com/image.jpg")
        message = Message(
            content="What's in this image?", role="user", _attachments=[image]
        )
        self.assertEqual(len(message._attachments), 1)
        self.assertIsInstance(message._attachments[0], Image)

    def test_message_to_dict(self):
        message = Message(content="Hello", role="user", name="Bill")
        message_dict = message.to_dict()
        self.assertEqual(message_dict["content"], "Hello")
        self.assertEqual(message_dict["role"], "user")
        self.assertEqual(message_dict["name"], "Bill")

    def test_message_from_dict(self):
        message_dict = {
            "content": "Hello",
            "role": "user",
            "name": "Bill",
            "_sticky": True,
            "_attachments": [
                {
                    "type": "image_url",
                    "data": {"url": "http://example.com/image.jpg"},
                }
            ],
        }
        message = Message.from_dict(message_dict)
        self.assertEqual(message.content, "Hello")
        self.assertEqual(message.role, "user")
        self.assertEqual(message.name, "Bill")
        self.assertTrue(message._sticky)
        self.assertEqual(len(message._attachments), 1)
        self.assertIsInstance(message._attachments[0], Image)


class TestImage(unittest.TestCase):
    def test_image_creation(self):
        image = Image(url="http://example.com/image.jpg", detail="high")
        self.assertEqual(image.url, "http://example.com/image.jpg")
        self.assertEqual(image.detail, "high")

    def test_image_to_dict(self):
        image = Image(url="http://example.com/image.jpg", detail="high")
        image_dict = image.to_dict()
        self.assertEqual(image_dict["type"], "image_url")
        self.assertEqual(
            image_dict["data"]["url"], "http://example.com/image.jpg"
        )
        self.assertEqual(image_dict["data"]["detail"], "high")

    def test_image_from_dict(self):
        image_dict = {
            "type": "image_url",
            "data": {"url": "http://example.com/image.jpg", "detail": "high"},
        }
        image = Image.from_dict(image_dict)
        self.assertEqual(image.url, "http://example.com/image.jpg")
        self.assertEqual(image.detail, "high")


if __name__ == "__main__":
    unittest.main()
