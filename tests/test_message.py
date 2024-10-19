import unittest
from gptcmd.message import (
    Image,
    Message,
    MessageRole,
    MessageThread,
    PopStickyMessageError,
    UnknownAttachment,
)

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
            Message(content="Hello", role=MessageRole.USER),
            Message(content="Hi", role=MessageRole.ASSISTANT),
        ]
        thread = MessageThread(name="test", messages=messages)
        self.assertEqual(len(thread), 2)
        self.assertEqual(thread[0].content, "Hello")
        self.assertEqual(thread[1].content, "Hi")

    def test_init_with_names(self):
        names = {MessageRole.USER: "Alice", MessageRole.ASSISTANT: "Mila"}
        thread = MessageThread(name="test", names=names)
        self.assertEqual(thread.names, names)


class TestMessageThread(unittest.TestCase):
    def setUp(self):
        self.thread = MessageThread(name="test")

    def test_append(self):
        self.thread.append(Message(content="Hello", role=MessageRole.USER))
        self.assertEqual(len(self.thread), 1)
        self.assertEqual(self.thread[0].content, "Hello")
        self.assertEqual(self.thread[0].role, MessageRole.USER)
        self.assertTrue(self.thread.dirty)

    def test_render(self):
        self.thread.append(
            Message(content="What is a cactus?", role=MessageRole.USER)
        )
        self.thread.append(
            Message(
                content=(
                    "A desert plant with thick, fleshy stems, sharp spines,"
                    " and beautiful, short-lived flowers."
                ),
                role=MessageRole.ASSISTANT,
            )
        )
        self.assertEqual(
            self.thread.render(),
            "user: What is a cactus?\nassistant: A desert plant with thick,"
            " fleshy stems, sharp spines, and beautiful, short-lived flowers.",
        )

    def test_render_custom_names(self):
        self.thread.names = {
            MessageRole.USER: "Bill",
            MessageRole.ASSISTANT: "Kevin",
        }
        self.thread.append(
            Message(content="What is a cactus?", role=MessageRole.USER)
        )
        self.thread.append(
            Message(
                content=(
                    "A desert plant with thick, fleshy stems, sharp spines,"
                    " and beautiful, short-lived flowers."
                ),
                role=MessageRole.ASSISTANT,
            )
        )
        self.assertEqual(
            self.thread.render(),
            "Bill: What is a cactus?\nKevin: A desert plant with thick, fleshy"
            " stems, sharp spines, and beautiful, short-lived flowers.",
        )

    def test_pop(self):
        self.thread.append(Message(content="Hello", role=MessageRole.USER))
        self.thread.append(Message(content="Hi", role=MessageRole.ASSISTANT))
        popped = self.thread.pop()
        self.assertEqual(len(self.thread), 1)
        self.assertEqual(popped.content, "Hi")
        self.assertEqual(popped.role, MessageRole.ASSISTANT)
        self.thread.pop()
        with self.assertRaises(IndexError):
            self.thread.pop()

    def test_pop_sticky(self):
        self.thread.append(
            Message(content="Hello", role=MessageRole.USER, sticky=True)
        )
        with self.assertRaises(PopStickyMessageError):
            self.thread.pop()

    def test_clear(self):
        self.thread.append(Message(content="Hello", role=MessageRole.USER))
        self.thread.append(Message(content="Hi", role=MessageRole.ASSISTANT))
        self.thread.clear()
        self.assertEqual(len(self.thread), 0)

    def test_clear_sticky(self):
        self.thread.append(
            Message(content="Hello", role=MessageRole.USER, sticky=True)
        )
        self.thread.append(Message(content="Hi", role=MessageRole.ASSISTANT))
        self.thread.clear()
        self.assertEqual(len(self.thread), 1)

    def test_flip(self):
        self.thread.append(Message(content="Hello", role=MessageRole.USER))
        self.thread.append(Message(content="Hi", role=MessageRole.ASSISTANT))
        flipped = self.thread.move(-1, 0)
        self.assertEqual(flipped.content, "Hi")
        self.assertEqual(self.thread[0].content, "Hi")
        self.assertEqual(self.thread[0].role, MessageRole.ASSISTANT)
        self.assertEqual(self.thread[1].content, "Hello")
        self.assertEqual(self.thread[1].role, MessageRole.USER)

    def test_rename(self):
        self.thread.append(Message(content="Hello", role=MessageRole.USER))
        self.thread.append(Message(content="Hi", role=MessageRole.ASSISTANT))
        self.thread.rename(role=MessageRole.ASSISTANT, name="GPT")
        self.assertEqual(self.thread[1].name, "GPT")

    def test_rename_limited_range(self):
        self.thread.append(Message(content="abc", role=MessageRole.USER))
        self.thread.append(Message(content="def", role=MessageRole.ASSISTANT))
        self.thread.append(Message(content="ghi", role=MessageRole.USER))
        self.thread.append(Message(content="jkl", role=MessageRole.USER))
        self.thread.rename(
            role=MessageRole.USER, name="Kevin", start_index=0, end_index=2
        )
        self.assertEqual(self.thread[0].name, "Kevin")
        self.assertIsNone(self.thread[1].name)
        self.assertIsNone(self.thread[2].name)
        self.assertIsNone(self.thread[3].name)

    def test_sticky(self):
        self.thread.append(Message(content="Hello", role=MessageRole.USER))
        self.thread.append(Message(content="Hi", role=MessageRole.ASSISTANT))
        self.thread.sticky(0, 1, True)
        self.assertTrue(self.thread[0].sticky)
        self.assertFalse(self.thread[1].sticky)

    def test_messages_property(self):
        self.thread.append(Message(content="Hello", role=MessageRole.USER))
        self.thread.append(Message(content="Hi", role=MessageRole.ASSISTANT))
        messages = self.thread.messages
        self.assertIsInstance(messages, tuple)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].content, "Hello")
        self.assertEqual(messages[1].content, "Hi")

    def test_to_dict(self):
        self.thread.append(Message(content="Hello", role=MessageRole.USER))
        self.thread.append(Message(content="Hi", role=MessageRole.ASSISTANT))
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
        self.assertEqual(thread[0].role, MessageRole.USER)
        self.assertEqual(thread[1].content, "Hi")
        self.assertEqual(thread[1].role, MessageRole.ASSISTANT)
        self.assertEqual(
            thread.names,
            {MessageRole.USER: "Alice", MessageRole.ASSISTANT: "Mila"},
        )


class TestMessage(unittest.TestCase):
    def test_message_creation(self):
        message = Message(content="Hello", role=MessageRole.USER)
        self.assertEqual(message.content, "Hello")
        self.assertEqual(message.role, MessageRole.USER)
        self.assertIsNone(message.name)
        self.assertFalse(message.sticky)
        self.assertEqual(message.attachments, [])

    def test_message_with_attachment(self):
        image = Image(url="http://example.com/image.jpg")
        message = Message(
            content="What's in this image?",
            role=MessageRole.USER,
            attachments=[image],
        )
        self.assertEqual(len(message.attachments), 1)
        self.assertIsInstance(message.attachments[0], Image)

    def test_message_to_dict(self):
        message = Message(content="Hello", role=MessageRole.USER, name="Bill")
        message_dict = message.to_dict()
        self.assertEqual(message_dict["content"], "Hello")
        self.assertEqual(message_dict["role"], MessageRole.USER)
        self.assertEqual(message_dict["name"], "Bill")

    def test_message_from_dict(self):
        message_dict = {
            "content": "Hello",
            "role": "user",
            "name": "Bill",
            "sticky": True,
            "attachments": [
                {
                    "type": "image_url",
                    "data": {"url": "http://example.com/image.jpg"},
                }
            ],
        }
        message = Message.from_dict(message_dict)
        self.assertEqual(message.content, "Hello")
        self.assertEqual(message.role, MessageRole.USER)
        self.assertEqual(message.name, "Bill")
        self.assertTrue(message.sticky)
        self.assertEqual(len(message.attachments), 1)
        self.assertIsInstance(message.attachments[0], Image)

    def test_message_unknown_attachment(self):
        message_dict = {
            "content": "",
            "role": "user",
            "attachments": [
                {
                    "type": "nonexistent_attachment",
                    "data": {"username": "kwebb"},
                }
            ],
        }
        message = Message.from_dict(message_dict)
        self.assertEqual(len(message.attachments), 1)
        self.assertIsInstance(message.attachments[0], UnknownAttachment)
        serialized_message = message.to_dict()
        self.assertEqual(
            message_dict["attachments"][0],
            serialized_message["attachments"][0],
        )


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
