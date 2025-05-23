# Large language model providers

Gptcmd uses instances of the `LLMProvider` abstract class to interact with large language models (LLMs). This document describes the `LLMProvider` abstract class and supporting infrastructure and demonstrates how to implement a simple custom provider.

## Overview

`gptcmd.llm.LLMProvider` is an [abstract base class](https://docs.python.org/3/glossary.html#term-abstract-base-class) located in `src/gptcmd/llm/__init__.py`. It defines the interface that all LLM providers must implement to work with Gptcmd. Below is an overview of the main components.

### Key methods

#### `from_config(cls, conf: Dict) -> LLMProvider`

* **Purpose**: A class method that instantiates the LLMProvider from a user configuration dictionary.
* **Usage**: This class method is used by the configuration system to instantiate `LLMProvider` classes.

#### `complete(self, messages: Sequence[Message]) -> LLMResponse`

* **Purpose**: Generate a response from the LLM given a collection of `Message` objects.
* **Usage**: This method should contain the logic that calls your LLM API and converts its response into an `LLMResponse` object.

#### `validate_api_params(self, params: Dict[str, Any]) -> Dict[str, Any]`

* **Purpose**: Validate and sanitize API parameters provided by the user.
* **Usage**: Ensure that only valid parameters are accepted and that they are within acceptable ranges or formats. This method should raise `InvalidAPIParameterError` for unknown parameter values or values that cannot be sanitized programmatically.

#### `get_best_model(self) -> str`

* **Purpose**: Return the name of the most capable model offered by this provider.
* **Usage**: This method helps in selecting a default model if none is otherwise configured.

#### `valid_models(self) -> Optional[Iterable[str]]`

* **Purpose**: Provide a collection of valid model names that can be used with this provider. If a list of valid models cannot be determined in this session, return `None`.
* **Usage**: Used during validation when switching the active model.

### Supporting classes and exceptions

#### `gptcmd.message.Message`

* **Purpose**: A [`dataclass`](https://docs.python.org/3/library/dataclasses.html) representing a message written by the user or LLM.
* **Usage**: Used throughout the application.

##### Key fields

Field | Type | Description
--- | --- | ---
`content` | `str` | The text of the message.
`role` | `gptcmd.message.MessageRole` | The conversational role of this message, such as `gptcmd.message.MessageRole.USER`.
`name` | `Optional[str]` | The user-provided name for this message.
`attachments` | `List[gptcmd.message.MessageAttachment]` | A list of rich attachments, such as images, associated with this message.
`metadata` | `Dict[str, Any]` | A dictionary of arbitrary metadata associated with this message, which can be used to get or set data particular to a specific provider (such as reasoning text, a digital signature, user requests for special handling, etc.). Since `metadata` is a field on `Message`, it can be accessed by any provider: it may be wise to, say, prefix metadata keys with the `LLMProvider`'s entry point name and an underscore for namespacing. Metadata values must be JSON serializable.

#### `gptcmd.llm.LLMResponse`

* **Purpose**: A [`dataclass`](https://docs.python.org/3/library/dataclasses.html) containing a `Message` generated by the `LLMProvider` in response to a user request, as well as optional metadata like token counts and cost estimates.
* **Usage**: Return this from your `complete` method.

##### Key fields

Field | Type | Description
--- | --- | ---
`message` | `gptcmd.message.Message` | The `Message` object containing the LLM's response to a user query.
`prompt_tokens` | `Optional[int]` | The number of tokens, as determined by the LLM's tokenizer, which the request (context) that generated this response contains.
`sampled_tokens` | `Optional[int]` | The number of tokens, as determined by the LLM's tokenizer, which this response contains.
`cost_in_cents` | `Optional[Union[int, Decimal]]` | An estimate of the cost, in US cents, of the request that generated this response.

#### Exceptions

* **`gptcmd.config.ConfigError`**: Raised by the `from_config` method when the provider cannot be configured.
* **`gptcmd.llm.CompletionError`**: Raised by the `complete` method when the LLM cannot generate a response.
* **`gptcmd.llm.InvalidAPIParameterError`**: Raised by the `validate_api_params` method when invalid API parameters are provided.

## Building an `LLMProvider`

To show how the process works, we'll build a simple `LLMProvider` implementation that mostly just responds with a copy of the user's request. To start, create a directory called `gptcmd-echo-provider`.

### Packaging metadata

In your `gptcmd-echo-provider` directory, create a file called `pyproject.toml` with the following content:

``` toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "gptcmd-echo-provider"
version = "0.1.0"
dependencies = ["gptcmd >= 2.0.0"]
```

More information about the `pyproject.toml` format can be found in the [relevant section of the Python Packaging Tutorial](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/).

Gptcmd uses a [packaging entry point](https://packaging.python.org/en/latest/specifications/entry-points/) to find external providers. The name of the entry point corresponds to the value of the `provider` option used to select it in a user account configuration. Add this to the end of `pyproject.toml`, which will make our new provider selectable with `provider="echo"` in an account configuration table:

``` toml
[project.entry-points."gptcmd.providers"]
echo = "gptcmd_echo_provider.echo:EchoProvider"
```

Create an `src` directory inside `gptcmd-echo-provider`. Inside that directory, create a subdirectory called `gptcmd_echo_provider`. Create an empty file at `gptcmd-echo-provider/src/gptcmd_echo_provider/__init__.py` so that Python considers this directory a package.

### Provider implementation

Create a new file, `gptcmd-echo-provider/src/gptcmd_echo_provider/echo.py`, with the following content:

``` python
from typing import Any, Dict, Iterable, Sequence

from gptcmd.llm import (
    CompletionError,
    InvalidAPIParameterError,
    LLMProvider,
    LLMResponse,
)
from gptcmd.message import Message, MessageRole


class EchoProvider(LLMProvider):
    @classmethod
    def from_config(cls, conf: Dict[str, Any]) -> "EchoProvider":
        # No config options supported
        return cls()

    def validate_api_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        raise InvalidAPIParameterError("API parameters are unsupported")
```

#### Implementing `complete`

For this provider, the `complete` method just returns a copy of whatever the user said last. Add this to `echo.py` (inside the `EchoProvider` class):

``` python
    def complete(self, messages: Sequence[Message]) -> LLMResponse:
        for msg in reversed(messages):
            if msg.role == MessageRole.USER:
                return LLMResponse(
                    Message(content=msg.content, role=MessageRole.ASSISTANT)
                )
        # We never reached a user message, so just throw an error
        raise CompletionError("Nothing to echo!")
```

#### Implementing model selection

Since this provider is just an example, we'll only support one model called `echo-1`. If this provider made multiple models available, we would provide the full list of options in the `valid_models` method. The currently selected model is available on the `model` attribute of an `LLMProvider` instance. Add this to `echo.py` (inside the class):

``` python
    def get_best_model(self) -> str:
        return "echo-1"

    @property
    def valid_models(self) -> Iterable[str]:
        return ("echo-1",)
```

### Testing the provider

Let's install, configure, and try out the new provider. From the `gptcmd-echo-provider` directory, run `pip install .` to install the provider package. During provider development, you might want to do an [editable install](https://pip.pypa.io/en/latest/topics/local-project-installs/) (`pip install -e .`) so that you don't need to reinstall the package after each change.

After the provider is installed, add a new account to your configuration file:

``` toml
[accounts.echotest]
provider="echo"
```

Start Gptcmd and test the provider:

```
(gpt-4o) account echotest
Switched to account 'echotest'
(echo-1) say Hello, world!
...
Hello, world!
```

### Optional features

#### User configuration

Configuration values can be extracted and passed to the created `LLMProvider` instance from its `from_config` constructor. For instance, we can add a configuration option to echo messages in reverse. First, add a constructor to the `EchoProvider` class:

``` python
    def __init__(self, backwards: bool = False, *args, **kwargs):
        self.backwards = backwards
        super().__init__(*args, **kwargs)
```

Then, replace the `from_config` method with:

``` python
    @classmethod
    def from_config(cls, conf: Dict[str, Any]) -> "EchoProvider":
        return cls(backwards=conf.get("backwards"))
```

In this example, `from_config` always succeeds. If `from_config` might throw an error (for instance, due to invalid user input, failed network requests, etc.), the method should raise `ConfigError` (in the `gptcmd.config` module).

Now, modify `complete`:

``` python
    def complete(self, messages: Sequence[Message]) -> LLMResponse:
        for msg in reversed(messages):
            if msg.role == MessageRole.USER:
                content = msg.content[::-1] if self.backwards else msg.content
                return LLMResponse(
                    Message(content=content, role=MessageRole.ASSISTANT)
                )
        # We never reached a user message, so just throw an error
        raise CompletionError("Nothing to echo!")
```

By default, the provider outputs messages as-is (in forward order):

```
(echo-1) say Hello, world!
...
Hello, world!
```

However, when we add `backwards=true` to the account configuration:

``` toml
[accounts.echotest]
provider="echo"
backwards=true
```

We get:

```
(echo-1) say Hello, world!
...
!dlrow ,olleH
(echo-1) say Was it Eliot's toilet I saw?
...
?was I teliot s'toilE ti saW
```

#### API parameters

To support API parameters, implement `validate_api_params`. We'll add a parameter to control how many times the user's message is echoed. Replace the `validate_api_params` method with:

``` python
    def validate_api_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        # Examine the provided parameters
        for param, value in params.items():
            if param == "repeat":
                if not isinstance(value, int):
                    raise InvalidAPIParameterError("Repeat must be an integer")
                # We must echo at least one time
                # If the user provides zero or a negative number, set it to 1
                params["repeat"] = max(1, value)
            else:  # An unsupported parameter
                raise InvalidAPIParameterError(
                    f"Parameter {param!r} not supported"
                )
        return params
```

Implement support for the new parameter in `complete`:

``` python
    def complete(self, messages: Sequence[Message]) -> LLMResponse:
        for msg in reversed(messages):
            if msg.role == MessageRole.USER:
                content = msg.content
                if "repeat" in self.api_params:
                    content *= self.api_params["repeat"]
                return LLMResponse(
                    Message(content=content, role=MessageRole.ASSISTANT)
                )
        # We never reached a user message, so just throw an error
        raise CompletionError("Nothing to echo!")
```

Test it:

```
(echo-1) say hello
...
hello
(echo-1) set repeat 3
repeat set to 3
(echo-1) retry
...
hellohellohello
(echo-1) set repeat -1
repeat set to 1
(echo-1) retry
...
hello
(echo-1) unset repeat
repeat unset
(echo-1) retry
...
hello
```

##### Default parameters

To define default values for API parameters, update the constructor to set them, and override `unset_api_param` to restore the default value when a default parameter is unset. We'll set a default value of 1 for the `repeat` parameter. Add a class variable to the `EchoProvider` class:

``` python
class EchoProvider(LLMProvider):
    DEFAULT_API_PARAMS: Dict[str, Any] = {"repeat": 1}
    # ...
```

Next, add a constructor:

``` python
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.update_api_params(self.__class__.DEFAULT_API_PARAMS)
```

And override `unset_api_param`:

``` python
    def unset_api_param(self, key: Optional[str] = None) -> None:
        super().unset_api_param(key)
        if key in self.__class__.DEFAULT_API_PARAMS:
            self.set_api_param(key, self.__class__.DEFAULT_API_PARAMS[param])
        elif key is None:  # Unset all parameters
            self.update_api_params(self.__class__.DEFAULT_API_PARAMS)
```

Then, we can simplify `complete`:

``` python
    def complete(self, messages: Sequence[Message]) -> LLMResponse:
        for msg in reversed(messages):
            if msg.role == MessageRole.USER:
                return LLMResponse(
                    Message(
                        content=msg.content * self.api_params["repeat"],
                        role=MessageRole.ASSISTANT,
                    )
                )
        # We never reached a user message, so just throw an error
        raise CompletionError("Nothing to echo!")
```

#### Message name field

If your `LLMProvider` implementation processes the `name` field set on `Message` objects, you'll need to advertise this support. Add a class variable called `SUPPORTED_FEATURES` containing the appropriate member of the `gptcmd.llm.LLMProviderFeature` [flag enumeration](https://docs.python.org/3/library/enum.html#enum.Flag). Import `LLMProviderFeature` from `gptcmd.llm` in your provider's module, then add this inside the class:

``` python
    SUPPORTED_FEATURES = LLMProviderFeature.MESSAGE_NAME_FIELD
```

If your class implements support for multiple `LLMProviderFeature`s, separate them with a pipe (`|`) character.

#### Message attachments

To implement support for message attachments, write a formatter function for each attachment type you support, decorated with the `register_attachment_formatter` decorator on your provider class. For `EchoProvider`, we'll convert images to a simple string representation. First, import `Image` from `gptcmd.message`, then add this function to `echo.py` (outside the class):

``` python
@EchoProvider.register_attachment_formatter(Image)
def format_image(img: Image) -> str:
    return f"img={img.url}"
```

Now, modify `complete` to process attachments in the correct place. For `EchoProvider`, we'll just add them to the response content. For a more functional provider, you might add them to an API request body:

``` python
    def complete(self, messages: Sequence[Message]) -> LLMResponse:
        for msg in reversed(messages):
            if msg.role == MessageRole.USER:
                content = msg.content
                for a in msg.attachments:
                    content += "\n" + self.format_attachment(a)
                return LLMResponse(
                    Message(content=content, role=MessageRole.ASSISTANT)
                )
        # We never reached a user message, so just throw an error
        raise CompletionError("Nothing to echo!")
```

Now, when we attach images, their URLs are echoed:

```
(echo-1) user hello!
'hello!' added as user
(echo-1) image http://example.com/image.jpg
Image added to 'hello!'
(echo-1) send
...
hello!
img=http://example.com/image.jpg
```

#### Streamed responses

If your `LLMProvider` implementation can stream parts of a response as they are generated, you'll need to advertise this support. Add a class variable called `SUPPORTED_FEATURES` containing the appropriate member of the `gptcmd.llm.LLMProviderFeature` [flag enumeration](https://docs.python.org/3/library/enum.html#enum.Flag). Import `LLMProviderFeature` from `gptcmd.llm` in your provider's module, then add this inside the class:

``` python
    SUPPORTED_FEATURES = LLMProviderFeature.RESPONSE_STREAMING
```

If your class implements support for multiple `LLMProviderFeature`s, separate them with a pipe (`|`) character.

The `stream` property on the `LLMProvider` instance will be set to `True` when a response should be streamed. If your `LLMProvider` only supports streaming under certain conditions (such as when certain models are used but not others), override the `stream` property getter to return `False` and the setter to raise `NotImplementedError` with an appropriate message in unsupported scenarios (you can use the already defined `LLMProvider._stream` attribute as a backing field). To enable streaming by default, set the property in your provider's constructor. Then, subclass `LLMResponse` to handle streams. In your `LLMResponse` implementation, you'll want to create a backing `Message` (that you update as the response streams in, so that user disconnections and runtime errors are handled gracefully), and implement an iterator to update this message and yield the text of the next chunk of the stream as a string. In `complete`, return your custom `LLMResponse` when `self.stream == True`.
