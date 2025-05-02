# Gptcmd
Gptcmd allows you to interact with large language models, such as OpenAI's GPT, efficiently in your terminal. Gptcmd can manage multiple concurrent "threads" of conversation, allowing for free and easy prompt experimentation and iteration. Individual messages can be manipulated, loaded from, and saved to files (both plain text and JSON), and API parameters are fully customizable. In short, Gptcmd is simple yet flexible, useful for both basic conversation and more involved prototyping.

## Getting started
Gptcmd requires [Python](https://python.org) 3.8.6 or later. It is available on PyPI, and can, for instance, be installed with `pip install gptcmd` at a command line shell. Running `gptcmd` at a shell starts the application. If Python's `bin` or `scripts` directory isn't on your path, you may need to launch the application with a command like `~/.local/bin/gptcmd` (depending on your system configuration). In most cases though, `gptcmd` should "just work".

If you'd like to use OpenAI models and you don't have an OpenAI account, you'll need to create one and [add some credit](https://platform.openai.com/account/billing/overview). $5 or so goes very far, [especially on `gpt-4.1-mini` or `gpt-4.1-nano`](#model-selection).

Gptcmd searches for provider credentials in its configuration file, falling back to the `OPENAI_API_KEY` environment variable if no key is provided in its configuration. If you'd like to use OpenAI models and you don't have an API key, you'll need to [generate a key](https://platform.openai.com/account/api-keys).

Once Gptcmd starts, it presents a prompt containing the name of the currently active model and waits for user input. Running the `quit` command (typing `quit` at the prompt and pressing <kbd>Return</kbd>) exits the program.

Gptcmd has a help facility that provides a list of available commands and brief usage hints for each. The `help` command with no arguments provides a list of available commands. Passing a command as an argument to `help` returns information on the selected command.

### Configuring Gptcmd
When Gptcmd starts for the first time, it generates a configuration file whose location depends on your operating system:

Platform | Config location
--- | ---
Windows | `%appdata%\gptcmd\config.toml`
MacOS | `~/Library/Application Support/gptcmd/config.toml`
Other | `$XDG_CONFIG_HOME/gptcmd/config.toml` or `~/.config/gptcmd/config.toml`

You may open Gptcmd's configuration file in a text editor to change application settings. The file contains comments that describe the available options. Configuration changes will be applied the next time Gptcmd is restarted.

### Simple conversation
The `say` command sends a message to the model:

```
(gpt-4o) say Hello, world!
...
Hello! How can I assist you today?
```

Gptcmd sends the entire conversation every time, never deleting history unless told to do so.

```
(gpt-4o) say I'm good! How are you?
...
I'm just a program, so I don't have feelings, but I'm here and ready to help you with anything you need!
(gpt-4o) say That's alright. Count from 1 to 5.
...
Sure! Here you go: 1, 2, 3, 4, 5.
(gpt-4o) say What are the next two numbers after that?
...
The next two numbers are 6 and 7.
```

The conversation can be cleared with the `clear` command, at which point any previous context will no longer be made available to the model:

```
(gpt-4o) clear
Delete 8 messages? (y/n)y
Cleared
(gpt-4o) say What are the next two numbers after that?
...
I apologize, but your request is unclear. Could you please provide more information or context? For example, if you're referring to a numerical pattern or sequence, sharing the sequence would help me assist you better.
```

### Viewing messages
The `first` and `last` commands view the first and last messages in the conversation respectively:

```
(gpt-4o) say Write a limerick about generative AI.
...
In the land of the silicon chip,  
Generative AI took a trip.  
With words it would play,  
In a curious way,  
Creating tales at the click of a lip.
(gpt-4o) first
user: What are the next two numbers after that?
(gpt-4o) last
assistant: In the land of the silicon chip,  
Generative AI took a trip.  
With words it would play,  
In a curious way,  
Creating tales at the click of a lip.
```

Providing an integer k as an argument shows the first/last k messages:

```
(gpt-4o) first 2
user: What are the next two numbers after that?
assistant: I apologize, but your request is unclear. Could you please provide more information or context? For example, if you're referring to a numerical pattern or sequence, sharing the sequence would help me assist you better.
(gpt-4o) last 3
assistant: I apologize, but your request is unclear. Could you please provide more information or context? For example, if you're referring to a numerical pattern or sequence, sharing the sequence would help me assist you better.
user: Write a limerick about generative AI.
assistant: In the land of the silicon chip,
Generative AI took a trip.
With words it would play,
In a curious way,
Creating tales at the click of a lip.
```

The `view` command shows the entire conversation:

```
(gpt-4o) view
user: What are the next two numbers after that?
assistant: I apologize, but your request is unclear. Could you please provide more information or context? For example, if you're referring to a numerical pattern or sequence, sharing the sequence would help me assist you better.
user: Write a limerick about generative AI.
assistant: In the land of the silicon chip,
Generative AI took a trip.
With words it would play,
In a curious way,
Creating tales at the click of a lip.
```

### Message ranges
Various Gptcmd commands work over ranges of messages in a conversation. Ranges are specified either as the index (position) of a single message, or a space-separated pair of the inclusive indices of the beginning and end of an interval of messages. Unlike in many programming languages, messages are one-indexed (i.e. `1` refers to the first message, `2` to the second, etc.). A dot (`.`) refers either to the entire conversation or, in place of a numeric index, to either the beginning or end of the conversation. Negative indexing is supported (`-1` refers to the last message, `-2` to the penultimate, and so on).

The `view` command accepts a range of messages as an argument. When provided, it only shows messages in the indicated range. Some example message range specifications follow:

```
(gpt-4o) view 1
user: What are the next two numbers after that?
(gpt-4o) view 2
assistant: I apologize, but your request is unclear. Could you please provide more information or context? For example, if you're referring to a numerical pattern or sequence, sharing the sequence would help me assist you better.
(gpt-4o) view 2 3
assistant: I apologize, but your request is unclear. Could you please provide more information or context? For example, if you're referring to a numerical pattern or sequence, sharing the sequence would help me assist you better.
user: Write a limerick about generative AI.
(gpt-4o) view -1
assistant: In the land of the silicon chip,
Generative AI took a trip.
With words it would play,
In a curious way,
Creating tales at the click of a lip.
(gpt-4o) view 3 .
user: Write a limerick about generative AI.
assistant: In the land of the silicon chip,
Generative AI took a trip.
With words it would play,
In a curious way,
Creating tales at the click of a lip.
(gpt-4o) view .
user: What are the next two numbers after that?
assistant: I apologize, but your request is unclear. Could you please provide more information or context? For example, if you're referring to a numerical pattern or sequence, sharing the sequence would help me assist you better.
user: Write a limerick about generative AI.
assistant: In the land of the silicon chip,
Generative AI took a trip.
With words it would play,
In a curious way,
Creating tales at the click of a lip.
```

### Conversation roles
Gptcmd messages can have one of three "roles": user, representing the end-user; assistant, representing the large language model; and system, used to inform the model's behaviour. System messages can be appended to the conversation with the `system` command:

```
(gpt-4o) system As a philosophical proof assistant, you prefer to use the technique of proof by contradiction at any opportunity. Therefore, whenever you are asked to prove something, you first assume that the proposition is false, then given this assumption, you attempt to find a contradiction.
'As a philosophical proof assistant, you prefer to use the...' added as system
(gpt-4o) say Prove that all cacti are succulents.
...
To prove that all cacti are succulents, let's employ proof by contradiction. We begin by assuming the opposite of what we want to prove—that not all cacti are succulents. This assumption asserts that there is at least one cactus that is not a succulent.

Now, let's examine the definitions involved:

1. **Cactus**: A cactus is a type of plant belonging to the family Cactaceae, which is well-adapted to arid environments. Cacti typically have thick, fleshy parts that store water, and they often have needles instead of leaves.

2. **Succulent**: A succulent is a plant that has thick, fleshy parts developed to retain water in arid climates or soil conditions. This is a broader category that includes many different plant families, including Cactaceae.

Under our assumption, there exists a cactus that does not fit the definition of a succulent. In other words, this hypothetical cactus would not be adapted for water storage, lacking the thick, fleshy parts that characterize succulents. However, such characteristics are fundamental to the biological adaptation seen in all cacti, given their native environments, which require water conservation.

Thus, the assumption leads to a contradiction with the basic biological characteristics and adaptations of cacti. As all known cacti possess the necessary attributes to be classified as succulents, our assumption is false.

Therefore, we conclude that all cacti are indeed succulents.
```

Similarly, user and assistant messages can be added with the `user` and `assistant` commands respectively. Since models like GPT are agnostic of the source of messages (i.e. they don't track their own responses and expect downstream applications to manage context), Gptcmd allows you to inject your own arbitrary conversation history to which the model can respond:

```
(gpt-4o) user What are the first five Fibonacci numbers?
'What are the first five Fibonacci numbers?' added as user
(gpt-4o) assistant 1, 1, 2, 3, 5.
'1, 1, 2, 3, 5.' added as assistant
(gpt-4o) say And the next five?
...
The next five Fibonacci numbers after 1, 1, 2, 3, 5 are 8, 13, 21, 34, and 55.
```

The `send` command sends the conversation in its current state to the model and requests a response:

```
(gpt-4o) user What are the first ten digits of pi?
'What are the first ten digits of pi?' added as user
(gpt-4o) send
...
The first ten digits of pi are 3.141592653.
```

In fact, the `say` command just adds a user message and sends the conversation:

```
(gpt-4o) say What are the first ten digits of pi?
...
The first ten digits of pi are 3.141592653.
```

With no arguments, the `user`, `assistant`, `system`, and `say` commands open an external text editor (based on your system or Gptcmd configuration) for message composition.

### Working with attachments
OpenAI's latest models, such as `gppt-4o`, support images alongside text content. Images can be attached to messages with the `image` command, which accepts two arguments: the location of the image, either a URL or path to a local file; and the index of the message to which the image should be attached (if unspecified, it defaults to the last). We'll ask GPT to describe an image by creating a user message and attaching an image from Wikimedia Commons:

```
(gpt-4o) user What's in this image?
"What's in this image?" added as user
(gpt-4o) image https://upload.wikimedia.org/wikipedia/commons/c/ce/Long_cane.jpg
Image added to "What's in this image?"
```

When viewing the conversation, an at sign before a message indicates an attachment (multiple at signs indicate multiple attachments):

```
(gpt-4o) view
@user: What's in this image?
```

Now, we can `send` our message to get a description:

```
(gpt-4o) send
...
This is a white cane, often used by individuals who are blind or visually impaired to aid in mobility and navigation. It has a handle, a long shaft, and a rounded tip.
```

Similarly, the `audio` command can be used to attach audio files to messages. Its syntax and operation is identical to the `image` command.

### Managing messages
The `pop` command with no argument deletes the last message of a conversation:

```
(gpt-4o) say Responding with only one word, tell me a female given name.
...
Alice.
(gpt-4o) pop
'Alice.' deleted
(gpt-4o) send
...
Sophia
(gpt-4o) pop
'Sophia' deleted
(gpt-4o) send
...
Emily
(gpt-4o) view
user: Responding with only one word, tell me a female given name.
assistant: Emily
```

Deleting the last message and resending the conversation is a very common action while experimenting with large language models, so Gptcmd includes a shortcut: the `retry` command:

```
(gpt-4o) say Responding with only one word, tell me a male given name.
...
David
(gpt-4o) retry
...
John
(gpt-4o) retry
...
William
```

Providing the index of a single message as an argument to `pop` deletes the specified message:

```
(gpt-4o) user abc
'abc' added as user
(gpt-4o) user def
'def' added as user
(gpt-4o) user ghi
'ghi' added as user
(gpt-4o) pop 2
'def' deleted
(gpt-4o) view
user: abc
user: ghi
```

The `move` command moves the message at the start of a range to the end of that range. This is often useful for adding a system message to conversations that previously didn't have one:

```
(gpt-4o) say Prove that pi is not exactly equal to 3.14628 without the use of any mathematical symbols.
...
To demonstrate that pi is not exactly equal to three point one four six two eight, we can refer to the nature of pi and how it has been studied and understood throughout history.

Pi is defined as the ratio of the circumference of a circle to its diameter. It is known to be an irrational number, meaning it cannot be exactly expressed as a finite decimal or a fraction with whole numbers. This characteristic implies that it has an infinite and non-repeating decimal expansion. Historical effort has been put into calculating the digits of pi, revealing many digits beyond the decimal point.

While three point one four six two eight might appear to be close to pi, it is only an approximation. The actual digits of pi, after the well-known initial digits three point one four, continue as one five nine two six five and so forth. Since pi is irrational, its decimal representation is infinite and non-repeating, and cannot completely coincide with any finite number, no matter how many digits it contains.

Thus, because three point one four six two eight ends after five decimal places and pi does not, we conclude that they cannot be exactly equal.
(gpt-4o) first
user: Prove that pi is not exactly equal to 3.14628 without the use of any mathematical symbols.
(gpt-4o) system As a philosophical proof assistant, you prefer to use the technique of proof by contradiction at any opportunity. Therefore, whenever you are asked to prove something, you first assume that the proposition is false, then given this assumption, you attempt to find a contradiction.
'As a philosophical proof assistant, you prefer to use the...' added as system
(gpt-4o) move -1 1
'As a philosophical proof assistant, you prefer to use the technique...' moved to start
(gpt-4o) view 1 2
system: As a philosophical proof assistant, you prefer to use the technique of proof by contradiction at any opportunity. Therefore, whenever you are asked to prove something, you first assume that the proposition is false, then given this assumption, you attempt to find a contradiction.
user: Prove that pi is not exactly equal to 3.14628 without the use of any mathematical symbols.
(gpt-4o) pop 3
'To demonstrate that pi is not exactly equal to three point one four...' deleted
(gpt-4o) send
...
To prove that pi is not exactly equal to three point one four six two eight, we begin with the assumption that pi is indeed exactly three point one four six two eight. Given this assumption, we need to find a contradiction.

Let's recall the nature of pi. By definition, pi is the ratio of the circumference of a circle to its diameter in Euclidean space, and it is known to be an irrational number. An irrational number is one that cannot be expressed as the exact quotient of two integers, meaning it has a non-repeating, non-terminating decimal expansion.

Now, consider the number three point one four six two eight. This number is clearly a rational number because it can be expressed as the fraction thirty one thousand four hundred sixty-two and eight ten-thousandths. Since three point one four six two eight is a terminating decimal, it can be expressed precisely as the division of two integers.

If pi were equal to three point one four six two eight, then pi would be rational. However, this contradicts the well-established fact that pi is irrational. This contradiction implies that our initial assumption must be false.

Therefore, we conclude that pi is not exactly equal to three point one four six two eight.
```

The `grep` command takes a [regular expression](https://en.wikipedia.org/wiki/Regular_expression) as an argument and searches the conversation for occurrences within its content, displaying the index and a small preview of each message that matches:

```
(gpt-4o) grep contra
1 (system): '...prefer to use the technique of proof by [contra]diction at any...'
3 (assistant): "...iven this assumption, we need to find a [contra]diction. Let's recall..."
(gpt-4o) grep \d+
2 (user): 'Prove that pi is not exactly equal to [3].[14628] without the use of any...'
```

The `edit` command with no arguments opens the contents of the last message in an external text editor for modification. Providing the index of a message to `edit` as an argument edits that message.

### Message streaming
The `stream` command toggles message streaming. By default, streaming is enabled, so long responses from the language model are output in real time as they are generated. While a message is being streamed, pressing <kbd>Control</kbd>+<kbd>c</kbd> causes Gptcmd to stop waiting for the message to generate fully, allowing other commands to be used. When streaming is disabled, Gptcmd retrieves an entire response for each query and displays it when it arrives.

### Model selection
The `model` command switches the active model. For instance, we can switch to [`gpt-4.1-nano`](https://openai.com/index/gpt-4-1/), a smaller, cheaper model offered by OpenAI:

```
(gpt-4o) model gpt-4.1-nano
Switched to model 'gpt-4.1-nano'
(gpt-4.1-nano) say Hello!
...
Hello! How can I assist you today?
(gpt-4.1-nano) model gpt-4o
Switched to model 'gpt-4o'
```

Similarly, if you've configured multiple accounts (such as to use non-OpenAI providers), the `account` command can be used to switch among them by providing the name of the account to use as an argument.

### API parameters
Gptcmd supports customization of [chat completion API parameters](https://platform.openai.com/docs/api-reference/chat/create), such as `max_tokens` and `temperature`. The `set` command sets an OpenAI API parameter. When setting a parameter, the first argument to `set` is the name of the parameter and the second argument is its value (valid Python literals are supported). A value of `None` is equivalent to sending `null` via the API.

The `max_tokens` parameter limits the number of [sampled tokens](https://platform.openai.com/tokenizer) returned by GPT. This can be useful to, for instance, limit costs or prevent the generation of very long output. Note that if `max_tokens` is reached, output may be cut off abruptly:

```
(gpt-4o) set max_tokens 50
max_tokens set to 50
(gpt-4o) say Describe generative AI in three paragraphs
...
Generative AI refers to a subset of artificial intelligence techniques that focus on creating new content or data rather than analyzing existing datasets. Unlike traditional AI models, which are primarily designed to classify, predict, or perform specific tasks, generative AI systems are equipped
```

The `temperature` parameter controls GPT's sampling temperature. A temperature of 0 causes GPT to be very deterministic:

```
(gpt-4o) set temperature 0
temperature set to 0
(gpt-4o) say Tell me a fun fact about generative AI.
...
A fun fact about generative AI is that it has been used to create entirely new pieces of art and music, sometimes even fooling experts into thinking they were crafted by humans. For instance, AI-generated paintings have been sold at prestigious art auctions for
(gpt-4o) retry
...
A fun fact about generative AI is that it has been used to create entirely new pieces of art and music, sometimes even fooling experts into thinking they were crafted by humans. For instance, AI-generated paintings have been sold at prestigious art auctions for
(gpt-4o) retry
...
A fun fact about generative AI is that it has been used to create entirely new pieces of art and music, sometimes even fooling experts into thinking they were crafted by humans. For instance, AI-generated paintings have been sold at prestigious art auctions for
```

The `unset` command, with an argument, reverts the specified API parameter to its default value. With no argument, it restores all API parameters to default. Here, we'll unset `max_tokens`, so that full length responses can again be generated:

```
(gpt-4o) unset max_tokens
max_tokens unset
```

Higher temperatures result in more apparent randomness, which can translate in some applications to increased creativity or decreased factual accuracy:

```
(gpt-4o) set temperature 0.75
temperature set to 0.75
(gpt-4o) retry
...
A fun fact about generative AI is that it has been used to create entirely new pieces of art and music, sometimes even fooling experts into thinking these creations were made by humans. For instance, in 2018, an AI-generated painting called "Portrait of Edmond de Belamy" was auctioned at Christie’s for $432,500, far exceeding its estimated price. This demonstrated not only the creative capabilities of generative AI but also its potential impact on the art world, challenging traditional notions of creativity and authorship.
(gpt-4o) retry
...
A fun fact about generative AI is that it can create entirely new and unique pieces of art, music, and even poetry. For instance, AI models like OpenAI's DALL-E can generate imaginative and surreal images from simple text prompts, blending concepts that might not typically go together—such as a "two-headed flamingo in a bustling cityscape." This ability to merge creativity with computational power showcases how generative AI can expand the boundaries of artistic expression, offering novel tools for artists and creators to explore new dimensions of their work.
(gpt-4o) retry
...
A fun fact about generative AI is that it has been used to create entirely new pieces of music in the style of famous composers. For instance, AI models have been trained on the works of classical composers like Bach or Mozart to generate new compositions that mimic their distinct styles. This has opened up exciting possibilities not just for music enthusiasts but also for the entertainment industry, where AI-generated music can be used in films, video games, and other media to enhance creativity and reduce production costs.
```

Too high, though, and GPT will just emit nonsense. To prevent the generation of an extremely large volume of output, we'll again set `max_tokens`:

```
(gpt-4o) set max_tokens 30
max_tokens set to 30
(gpt-4o) set temperature 2
temperature set to 2
(gpt-4o) retry
...
A fun fact about generative AI is that it's unique nature sometimes find unexpected parallels in non-modern multipart generators like Soukawi Internet authored phoenix drôle mime
```

Another useful parameter is `timeout` which controls how long (in seconds) Gptcmd waits for a response from GPT:

```
(gpt-4o) set timeout 0.25
timeout set to 0.25
(gpt-4o) say Hello!
...
Request timed out.
```

The `set` command with no arguments shows all set API parameters:

```
(gpt-4o) set
max_tokens: 30
temperature: 2
timeout: 0.25
(gpt-4o) unset
Unset all parameters
```

### Names
GPT allows mesages to be annotated with the name of their author. The `name` command sets the name to be sent with all future messages of the specified role. Its first argument is the role to which this new name should be applied, and its second is the name to use:

```
(gpt-4o) name user Michael
user set to 'Michael'
(gpt-4o) say Hello! What's my name?
...
Hello! You mentioned your name is Michael. How can I assist you today?
```

With no arguments, `name` shows currently set names:

```
(gpt-4o) name
user: Michael
```

The `unname` command removes a name definition to be sent with future messages. With a role passed as an argument, it unsets the name definition for that role. With no arguments, it unsets all definitions. Any previously annotated messages are unaffected:

```
(gpt-4o) view
Michael: Hello!
assistant: Hello! You mentioned your name is Michael. How can I assist you today?
```

Name annotations are useful for providing one- or multi-shot prompts to GPT, in which example user and assistant messages help inform future responses:

```
(gpt-4o) system You are a helpful assistant who understands many languages very well, but can only speak Spanish and therefore you always respond in that language.
'You are a helpful assistant who understands many languages...' added as system
(gpt-4o) name system example_user
system set to 'example_user'
(gpt-4o) system Hello!
'Hello!' added as 'example_user' (system)
(gpt-4o) name system example_assistant
system set to 'example_assistant'
(gpt-4o) system ¡Hola! ¿Cómo estás?
'¡Hola! ¿Cómo estás?' added as 'example_assistant' (system)
(gpt-4o) view
system: You are a helpful assistant who understands many languages very well, but can only speak Spanish and therefore you always respond in that language.
example_user: Hello!
example_assistant: ¡Hola! ¿Cómo estás?
(gpt-4o) say Qu'est-ce que amazon.com?
...
Amazon.com es una empresa de comercio electrónico y tecnología que ofrece una amplia gama de productos y servicios en línea. Originalmente fundada en 1994 por Jeff Bezos como una librería en línea, Amazon se ha expandido para vender prácticamente de todo, desde electrónica hasta ropa, alimentos y servicios de computación en la nube, como AWS (Amazon Web Services). La empresa también produce dispositivos electrónicos, como el Kindle y dispositivos de la línea Echo con Alexa. Además, Amazon ofrece servicios de transmisión de video y música mediante Amazon Prime Video y Amazon Music, respectivamente.
```

The `rename` command changes the name set on existing messages in the conversation. The command has two required arguments and one optional argument: the role to affect, the range of messages to affect, and (optionally) the name to set (if omitted, the name is cleared). For instance, `rename assistant .` clears the name on all assistant messages in the conversation where a name is set, `rename user 1 Paul` sets the name of the first message to "Paul" if it is a user message, and `rename system 2 5 Mitchell` sets the name of all system messages in the second through fifth to "Mitchell".

### Sticky messages
Messages can be marked "sticky", so deletion, renaming, and similar modifications do not affect them. This is often useful for system messages and example context that you don't wish to delete accidentally. The sticky command takes the range of messages to sticky as an argument:

```
(gpt-4o) system You are a Python programmer. Therefore, when responding, you write in Python source code exclusively.
'You are a Python programmer. Therefore, when responding, you...' added as system
(gpt-4o) sticky .
1 message stickied
```

Now that the message is sticky, `clear` does not affect it, and its sticky status is indicated by an asterisk:

```
(gpt-4o) say Find the nth Fibonacci number.
...
def fibonacci(n):
    if n <= 0:
        raise ValueError("n must be a positive integer.")
    elif n == 1:
        return 0
    elif n == 2:
        return 1

    a, b = 0, 1
    for _ in range(2, n):
        a, b = b, a + b
    return b

# Example usage:
# nth_fibonacci = fibonacci(10)
# print(nth_fibonacci)  # Output: 34
(gpt-4o) clear
Delete 2 messages? (y/n)y
Cleared
(gpt-4o) view
*system: You are a Python programmer. Therefore, when responding, you write in Python source code exclusively.
```

Similarly, `pop` is blocked:

```
(gpt-4o) pop
That message is sticky; unsticky it first
```

The `unsticky` command makes all sticky messages in the specified range no longer sticky:

```
(gpt-4o) unsticky .
1 message unstickied
(gpt-4o) pop
'You are a Python programmer. Therefore, when responding, you write...' deleted
```

### Message metadata
Gptcmd allows arbitrary [key–value metadata](https://en.wikipedia.org/wiki/Name%E2%80%93value_pair) to be stored with each message. This might be useful, for instance, to store personal notes with messages, or as an interface to enable special features in external large language model providers (consult external package documentation for details).

Providing a key `k` and value `v` to the `meta` command stores `v` at `k` on the last message:

```
(gpt-4o) user This is a test.
'This is a test.' added as user
(gpt-4o) meta notes "This is a test of message metadata."
notes set to 'This is a test of message metadata.' on 'This is a test.
```

Valid JSON literals are supported in metadata values:

```
(gpt-4o) meta list [1,2,3]
list set to [1, 2, 3] on 'This is a test.'
(gpt-4o) meta obj {"key1": "value1", "key2": true}
obj set to {'key1': 'value1', 'key2': True} on 'This is a test.'
```

Providing just a key shows the associated value:

```
(gpt-4o) meta list
[1, 2, 3]
(gpt-4o) meta list2
'list2 not set'
```

With no arguments, `meta` shows all keys set on the last message:

```
(gpt-4o) meta
notes: 'This is a test of message metadata.'
list: [1, 2, 3]
obj: {'key1': 'value1', 'key2': True}
```

Providing an index as the first argument to `meta` operates on the selected message:

```
(gpt-4o) user Second message
'Second message' added as user
(gpt-4o) meta 1 list
[1, 2, 3]
(gpt-4o) meta 1 list2 [4,5,6]
list2 set to [4, 5, 6] on 'This is a test.'
```

The `unmeta` command deletes a key–value pair. Similarly to `meta`, it accepts an index as its first argument, operating on the last message if no index is provided:

```
(gpt-4o) unmeta 1 list2
list2 unset on 'This is a test.'
(gpt-4o) meta 1 list2
'list2 not set'
```

With no key specified, `unmeta` deletes all keys:

```
(gpt-4o) unmeta 1
delete 3 items on 'This is a test.'? (y/n)y
Unset all metadata on 'This is a test.'
(gpt-4o) meta 1
No metadata set on 'This is a test.'
(gpt-4o) clear
Delete 2 messages? (y/n)y
Cleared
```

### Message threads
Until this point, we have been engaging in a single conversation (or series of conversations) with the model. However, Gptcmd supports the creation and maintenance of several concurrent conversation "threads".

Gptcmd starts in the "detached thread", a scratch area intended for quick conversation. A new, named conversation thread can be created from the current thread with the `thread` command, which takes a name for the new thread as an argument:

```
(gpt-4o) say Responding only using ASCII/Unicode symbols and without narrative explanation, what is the closed-form formula to calculate the nth Fibonacci number?
...
F(n) = (φ^n - ψ^n) / √5

where:
φ = (1 + √5) / 2
ψ = (1 - √5) / 2
(gpt-4o) thread induction
Switched to new thread 'induction'
```

By default, the prompt changes to indicate the current thread. All messages have been copied:

```
induction(gpt-4o) view
user: Responding only using ASCII/Unicode symbols and without narrative explanation, what is the closed-form formula to calculate the nth Fibonacci number?
assistant: F(n) = (φ^n - ψ^n) / √5

where:
φ = (1 + √5) / 2
ψ = (1 - √5) / 2
```

The `thread` command with no argument switches back to the detached thread:

```
induction(gpt-4o) thread
detached thread
(gpt-4o) say Tell me a fun fact about Braille.
...
Braille was invented by Louis Braille, who was inspired by a tactile military code called "night writing" developed by Charles Barbier, intended for soldiers to communicate silently and without light.
```

Passing the name of an existing thread as an argument to `thread` switches to that thread. Once created, threads are completely independent:

```
(gpt-4o) last 3
assistant: F(n) = (φ^n - ψ^n) / √5

where:
φ = (1 + √5) / 2
ψ = (1 - √5) / 2
user: Tell me a fun fact about Braille.
assistant: Braille was invented by Louis Braille, who was inspired by a tactile military code called "night writing" developed by Charles Barbier, intended for soldiers to communicate silently and without light.
(gpt-4o) thread induction
Switched to thread 'induction'
induction(gpt-4o) last 3
user: Responding only using ASCII/Unicode symbols and without narrative explanation, what is the closed-form formula to calculate the nth Fibonacci number?
assistant: F(n) = (φ^n - ψ^n) / √5

where:
φ = (1 + √5) / 2
ψ = (1 - √5) / 2
```

When running `retry` in a named thread, Gptcmd asks whether you'd like to create a new thread, preserving both responses (this can be changed in Gptcmd configuration):

```
induction(gpt-4o) say Responding in a short paragraph and without showing your algebra, prove by induction that this formula is equivalent to the recursive definition.
...
To prove the closed-form formula, known as Binet's formula, is equivalent to the recursive definition of the Fibonacci sequence, use mathematical induction. First, verify the base cases: for \( n = 0 \) and \( n = 1 \), evaluate the formula and confirm it gives the correct Fibonacci numbers \( F(0) = 0 \) and \( F(1) = 1 \). Next, assume the formula is true for \( n = k \) and \( n = k + 1 \), meaning \( F(k) \) and \( F(k+1) \) are correct. Prove it for \( n = k + 2 \) by showing that substituting these into the recursive relation \( F(k+2) = F(k+1) + F(k) \) satisfies the formula. The linear recurrence relations of φ and ψ ensure that φ and ψ raised to any integer power adhere to the Fibonacci sequence, maintaining the truth of the expression for all \( n \). This confirms the formula's validity by induction.
induction(gpt-4o) retry
Create thread 'induction2'? (y/n)y
Switched to new thread 'induction2'
...
To prove by induction that the closed-form formula for the nth Fibonacci number is equivalent to the recursive definition, we start with the base cases. For n=0 and n=1, the formula gives F(0) = 0 and F(1) = 1, which match the recursive definition. For the inductive step, assume that F(k) and F(k+1) are true as per the formula for some k. Then, F(k+2) can be written as F(k+2) = φ^(k+2)/√5 - ψ^(k+2)/√5, which simplifies to φ^k+1 + φ^k/√5 after using the induction hypothesis and algebraic manipulation with φ and ψ properties, thus matching the recursive definition F(k+2) = F(k+1) + F(k). This closes the induction, showing the equivalence of the closed-form and recursive definitions for all n.
```

We can continue our conversation from here:

```
induction2(gpt-4o) say Explain this proof to a five-year-old.
...
Okay, imagine you have a cool way to get into a big number treasure chest called the Fibonacci chest! There are two ways to find the "number treasure": one is building steps one by one (like adding the last two steps to get the next step), which is like adding blocks — 0, 1, 1, 2, 3, 5... And there's a magic code (the special formula) that lets you jump right to any step you want, as long as you know which number step it is. When you try both ways, they both give you the same number treasure every time you check a step, starting with the first hood on up. Isn't that neat? So whether you build step by step or use your special code, the treasure you find is always the same! 🧡
```

Or return to the original response before we ran `retry`:

```
induction2(gpt-4o) thread induction
Switched to thread 'induction'
```

The `copy` command copies all messages in the specified range and appends the copies to the thread provided, creating it if it doesn't exist. If no thread is provided, `copy` copies messages to the detached thread:

```
induction(gpt-4o) thread
detached thread
(gpt-4o) clear
Delete 4 messages? (y/n)y
Cleared
(gpt-4o) thread induction2
Switched to thread 'induction2'
induction2(gpt-4o) copy 1 2
Selecting 2 messages
First message selected: 'Responding only using ASCII/Unicode symbols and...'
Last message selected: 'F(n) = (φ^n - ψ^n) / √5 where: φ = (1 + √5) / 2 ψ =...'
Copy to detached thread? (y/n)y
Copied
induction2(gpt-4o) thread
detached thread
(gpt-4o) say Write a C function that implements this closed-form formula without any narrative explanation.
...
#include <math.h>

int fibonacci(int n) {
    double phi = (1 + sqrt(5)) / 2;
    double psi = (1 - sqrt(5)) / 2;
    return round((pow(phi, n) - pow(psi, n)) / sqrt(5));
}
```

The `threads` command lists the named threads present in this session:

```
(gpt-4o) threads
induction2 (6 messages)
induction (4 messages)
(4 detached messages)
```

The `delete` command, with the name of a thread passed as an argument, deletes the specified thread:

```
(gpt-4o) delete induction
Deleted thread induction
(gpt-4o) threads
induction2 (6 messages)
(4 detached messages)
```

With no argument, `delete` deletes **all** named threads in this session:

```
(gpt-4o) delete
Delete 1 thread? (y/n)y
Deleted
(gpt-4o) threads
No threads
(4 detached messages)
```

### Working with files
The `transcribe` command writes a plain-text transcript of the current thread to a text file, overwriting any existing file contents. It takes the path to the file to write as an argument.

The `save` command writes all named threads to a JSON file, overwriting any existing file contents. It takes the path to the file to write as an argument. With no argument, `save` writes to the most recently loaded or saved JSON file in the current session.

The `load` command loads all saved named threads from a JSON file in the format written by `save`, merging them into the current session. If there is a naming conflict between a thread in the current session and a thread in the file to load, the thread in the file wins. The `load` command takes the path of the file to load as an argument.

The `write` command writes the contents of the last message of the current thread to a text file, overwriting any existing file contents. This command is particularly useful when working with source code. It takes the path to the file to write as an argument.

The `read` command appends a new message to the current thread containing the text content of the specified file. It takes two arguments: the path of the file to read and the role of the new message. For instance, `read prompt.txt system` reads the content of `prompt.txt` appending it as a new system message.

## Command line parameters
Gptcmd supports a few command line parameters:

```
$ gptcmd -h
usage: gptcmd [-h] [-c CONFIG] [-t THREAD] [-m MODEL] [-a ACCOUNT] [--version] [path]

positional arguments:
  path                  The path to a JSON file of named threads to load on launch

options:
  -h, --help            show this help message and exit
  -c CONFIG, --config CONFIG
                        The path to a Gptcmd configuration file to use for this session
  -t THREAD, --thread THREAD
                        The name of the thread to switch to on launch
  -m MODEL, --model MODEL
                        The name of the model to switch to on launch
  -a ACCOUNT, --account ACCOUNT
                        The name of the account to switch to on launch
  --version             Show version and exit
```
