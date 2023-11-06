# Gptcmd
Gptcmd allows you to interact with OpenAI's chat-based models (`gpt-3.5-turbo` and, if available to you, `gpt-4`) efficiently in your terminal. Gptcmd can manage multiple concurrent "threads" of conversation, allowing for free and easy prompt experimentation and iteration. Individual messages can be manipulated, loaded from, and saved to files (both plain text and JSON), and API parameters are fully customizable. In short, Gptcmd is simple yet flexible, useful for both basic conversation and more involved prototyping.

## Getting started
Gptcmd requires [Python](https://python.org) 3.7.1 or later. It is available on PyPI, and can, for instance, be installed with `pip install gptcmd` at a command line shell. Running `gptcmd` at a shell starts the application. If Python's `bin` or `scripts` directory isn't on your path, you may need to launch the application with a command like `~/.local/bin/gptcmd` (depending on your system configuration). In most cases though, `gptcmd` should "just work".

If you don't have an OpenAI account, you'll need to create one and [add your credit card](https://platform.openai.com/account/billing/overview). To manage costs, you can [set a monthly hard limit](https://platform.openai.com/account/billing/limits) ($5 or so goes very far, especially on `gpt-3.5-turbo`).

Gptcmd searches for an OpenAI API key in the `OPENAI_API_KEY` environment variable. If no key was found, Gptcmd will ask for it at launch. If you don't have an API key, you'll need to [generate a key](https://beta.openai.com/account/api-keys).

Once Gptcmd starts, it presents a prompt containing the name of the currently active model and waits for user input. Running the `quit` command (typing `quit` at the prompt and pressing <kbd>Return</kbd>) exits the program.

Gptcmd has a help facility that provides a list of available commands and brief usage hints for each. The `help` command with no arguments provides a list of available commands. Passing a command as an argument to `help` returns information on the selected command.

### Simple conversation
The `say` command sends a message to GPT:

```
(gpt-3.5-turbo) say Hello, world!
...
Hello there! How can I assist you today?
```

Gptcmd sends the entire conversation every time, never deleting history unless told to do so.

```
(gpt-3.5-turbo) say I'm good! How are you?
...
As an AI language model, I don't have feelings but I'm functioning properly. How may I assist you today?
(gpt-3.5-turbo) say That's alright. Count from 1 to 5.
...
Sure, here it is:
1
2
3
4
5
(gpt-3.5-turbo) say What are the next two numbers after that?
...
The next two numbers after 5 are 6 and 7.
```

The conversation can be cleared with the `clear` command, at which point any previous context will no longer be made available to GPT:

```
(gpt-3.5-turbo) clear
Delete 8 messages? (y/n)y
OK
(gpt-3.5-turbo) say What are the next two numbers after that?
...
As an AI language model, I would need more context to provide an accurate answer. Please provide the sequence of numbers or the pattern to continue with.
```

### Viewing messages
The `first` and `last` commands view the first and last messages in the conversation respectively:

```
(gpt-3.5-turbo) say Write a limerick about generative AI.
...
There once was a generative AI
Whose skills could surely apply
With patterns and sequences
It made new appearances
And impressed us with each new try
(gpt-3.5-turbo) first
user: What are the next two numbers after that?
(gpt-3.5-turbo) last
assistant: There once was a generative AI
Whose skills could surely apply
With patterns and sequences
It made new appearances
And impressed us with each new try
```

Providing an integer k as an argument shows the first/last k messages:

```
(gpt-3.5-turbo) first 2
user: What are the next two numbers after that?
assistant: As an AI language model, I would need more context to provide an accurate answer. Please provide the sequence of numbers or the pattern to continue with.
(gpt-3.5-turbo) last 3
assistant: As an AI language model, I would need more context to provide an accurate answer. Please provide the sequence of numbers or the pattern to continue with.
user: Write a limerick about generative AI.
assistant: There once was a generative AI
Whose skills could surely apply
With patterns and sequences
It made new appearances
And impressed us with each new try
```

The `view` command shows the entire conversation:

```
(gpt-3.5-turbo) view
user: What are the next two numbers after that?
assistant: As an AI language model, I would need more context to provide an accurate answer. Please provide the sequence of numbers or the pattern to continue with.
user: Write a limerick about generative AI.
assistant: There once was a generative AI
Whose skills could surely apply
With patterns and sequences
It made new appearances
And impressed us with each new try
```

### Message ranges
Various Gptcmd commands work over ranges of messages in a conversation. Ranges are specified either as the index (position) of a single message, or a space-separated pair of the inclusive indices of the beginning and end of an interval of messages. Unlike in many programming languages, messages are one-indexed (i.e. `1` refers to the first message, `2` to the second, etc.). A dot (`.`) refers either to the entire conversation or, in place of a numeric index, to either the beginning or end of the conversation. Negative indexing is supported (`-1` refers to the last message, `-2` to the penultimate, and so on).

The `view` command accepts a range of messages as an argument. When supplied, it only shows messages in the indicated range. Some example message range specifications follow:

```
(gpt-3.5-turbo) view 1
user: What are the next two numbers after that?
(gpt-3.5-turbo) view 2
assistant: As an AI language model, I would need more context to provide an accurate answer. Please provide the sequence of numbers or the pattern to continue with.
(gpt-3.5-turbo) view 2 3
assistant: As an AI language model, I would need more context to provide an accurate answer. Please provide the sequence of numbers or the pattern to continue with.
user: Write a limerick about generative AI.
(gpt-3.5-turbo) view -1
assistant: There once was a generative AI
Whose skills could surely apply
With patterns and sequences
It made new appearances
And impressed us with each new try
(gpt-3.5-turbo) view 3 .
user: Write a limerick about generative AI.
assistant: There once was a generative AI
Whose skills could surely apply
With patterns and sequences
It made new appearances
And impressed us with each new try
(gpt-3.5-turbo) view .
user: What are the next two numbers after that?
assistant: As an AI language model, I would need more context to provide an accurate answer. Please provide the sequence of numbers or the pattern to continue with.
user: Write a limerick about generative AI.
assistant: There once was a generative AI
Whose skills could surely apply
With patterns and sequences
It made new appearances
And impressed us with each new try
```

### Conversation roles
OpenAI's API supports messages of three "roles": user, representing the end-user; assistant, representing the GPT AI; and system, used to inform the AI's behaviour. System messages can be appended to the conversation with the `system` command:

```
(gpt-3.5-turbo) system As a philosophical proof assistant, you prefer to use the technique of proof by contradiction at any opportunity. Therefore, whenever you are asked to prove something, you first assume that the proposition is false, then given this assumption, you attempt to find a contradiction.
OK
(gpt-3.5-turbo) say Prove that all cacti are succulents.
...
To prove that all cacti are succulents, we will use proof by contradiction. We will assume that there exists a cactus that is not a succulent and show that this leads to a contradiction.

Assume that there exists a cactus that is not a succulent. This means that there is a cactus that does not have the characteristic of storing water in its stems or leaves.

However, it is well-known that all cacti have the characteristic of storing water in their stems or leaves, as this is an essential adaptation for surviving in arid environments. Therefore, our assumption that there exists a cactus that is not a succulent is false.

Since we have shown that the assumption that there exists a cactus that is not a succulent leads to a contradiction, we can conclude that all cacti are succulents.
```

Similarly, user and assistant messages can be added with the `user` and `assistant` commands respectively. Since GPT itself is agnostic of the source of messages (i.e. it doesn't track its own responses and expects downstream applications to manage context), Gptcmd allows you to inject your own arbitrary conversation history to which GPT can respond:

```
(gpt-3.5-turbo) user What are the first five Fibanacci numbers?
OK
(gpt-3.5-turbo) assistant 1, 1, 2, 3, 5.
OK
(gpt-3.5-turbo) say And the next five?
...
8, 13, 21, 34, 55.
```

The `send` command sends the conversation in its current state to GPT and requests a response:

```
(gpt-3.5-turbo) user What are the first ten digits of pi?
OK
(gpt-3.5-turbo) send
...
3.141592653
```

In fact, the `say` command just adds a user message and sends the conversation:

```
(gpt-3.5-turbo) say What are the first ten digits of pi?
...
3.141592653
```

### Managing messages
The `pop` command with no argument deletes the last message of a conversation:

```
(gpt-3.5-turbo) say Tell me a female given name.
...
Sophia.
(gpt-3.5-turbo) pop
'Sophia' deleted
(gpt-3.5-turbo) send
...
Lila
(gpt-3.5-turbo) pop
'Lila' deleted
(gpt-3.5-turbo) send
...
Emily.
(gpt-3.5-turbo) view
user: Tell me a female given name.
assistant: Emily.
```

Deleting the last message and resending the conversation is a very common action while experimenting with GPT models, so Gptcmd includes a shortcut: the `retry` command:

```
(gpt-3.5-turbo) say Tell me a male given name.
...
David
(gpt-3.5-turbo) retry
...
John
(gpt-3.5-turbo) retry
...
William
```

Providing the index of a single message as an argument to `pop` deletes the specified message:

```
(gpt-3.5-turbo) user abc
OK
(gpt-3.5-turbo) user def
OK
(gpt-3.5-turbo) user ghi
OK
(gpt-3.5-turbo) pop 2
'def' deleted
(gpt-3.5-turbo) view
user: abc
user: ghi
```

The `flip` command moves the last message to the start of the conversation. This is often useful for adding a system message to conversations that previously didn't have one:

```
(gpt-3.5-turbo) say Prove that pi is not exactly equal to 3.14628.
...
Pi is a mathematical constant representing the ratio of a circle's circumference to its diameter. Its decimal representation goes on infinitely without repeating. The first few digits of pi are 3.14159... and not 3.14628.

One way to prove that pi is not exactly equal to 3.14628 is to show that the difference between the two values is non-zero.

Let's subtract 3.14628 from pi:

pi - 3.14628 = 3.14159... - 3.14628 = -0.00469...

The result is a negative number, which means that pi is smaller than 3.14628. Therefore, pi cannot be exactly equal to 3.14628.

We can also use the fact that pi is an irrational number, which means that it cannot be expressed as a simple fraction or a finite decimal. In other words, pi cannot be written as a terminating or repeating decimal like 3.14628.

Therefore, we can conclude that pi is not exactly equal to 3.14628.
(gpt-3.5-turbo) first
user: Prove that pi is not exactly equal to 3.14628.
(gpt-3.5-turbo) system As a philosophical proof assistant, you prefer to use the technique of proof by contradiction at any opportunity. Therefore, whenever you are asked to prove something, you first assume that the proposition is false, then given this assumption, you attempt to find a contradiction.
OK
(gpt-3.5-turbo) flip
'As a philosophical proof assistant, you prefer to use the...' moved to start
(gpt-3.5-turbo) view 1 2
system: As a philosophical proof assistant, you prefer to use the technique of proof by contradiction at any opportunity. Therefore, whenever you are asked to prove something, you first assume that the proposition is false, then given this assumption, you attempt to find a contradiction.
user: Prove that pi is not exactly equal to 3.14628.
(gpt-3.5-turbo) pop 3
"Pi is a mathematical constant representing the ratio of a circle's..." deleted
(gpt-3.5-turbo) send
...
Assume that pi is exactly equal to 3.14628.

However, we know that pi is a mathematical constant that represents the ratio of a circle's circumference to its diameter. This means that pi is an irrational number, which cannot be expressed as a finite decimal or fraction.

But 3.14628 is a finite decimal, which means it cannot represent the irrational number pi exactly.

Therefore, our assumption that pi is exactly equal to 3.14628 leads to a contradiction.

Thus, we can conclude that pi is not exactly equal to 3.14628.
```

### Message streaming
The `stream` command toggles OpenAI message streaming. When streaming is enabled, long responses from GPT are output in real time as they are generated. While a message is being streamed, pressing <kbd>Control</kbd>+<kbd>c</kbd> causes Gptcmd to stop waiting for the message to generate fully, so other commands can be used. Note that if using gpt-4, Gptcmd's gpt-4 cost estimator is incompatible with streamed responses.

### API parameters
Gptcmd supports customization of [chat completion API parameters](https://platform.openai.com/docs/api-reference/chat/create), such as `temperature` and `frequency_penalty`. The `set` command sets an OpenAI API parameter. When setting a parameter, the first argument to `set` is the name of the parameter and the second argument is its value (valid Python literals are supported). A value of `None` is equivalent to sending `null` via the API.

The `temperature` parameter controls GPT's sampling temperature. A temperature of 0 causes GPT to be very deterministic:

```
(gpt-3.5-turbo) set temperature 0
OK
(gpt-3.5-turbo) say Tell me a fun fact about generative AI.
...
Generative AI can create art that is so realistic that it has been sold at auction for over $400,000. In 2018, a portrait created by a generative AI program called "Edmond de Belamy" was sold at Christie's auction house in New York City. This marked the first time that a piece of AI-generated art had been sold at a major auction house.
(gpt-3.5-turbo) retry
...
Generative AI can create art that is so realistic
```
(rest of identical output omitted)
```
(gpt-3.5-turbo) retry
...
Generative AI can create art that is so realistic
```
(rest of identical output omitted)

Higher temperatures result in more apparent randomness, which can translate in some applications to increased creativity or decreased factual accuracy:

```
(gpt-3.5-turbo) set temperature 0.75
OK
(gpt-3.5-turbo) retry
...
Generative AI can create music that is so realistic, it is difficult to distinguish from compositions created by human composers. In fact, a piece of music composed by an AI program called AIVA was accepted by the American Society of Composers, Authors, and Publishers (ASCAP), making it the first AI-generated piece of music to be recognized by a professional music organization.
(gpt-3.5-turbo) retry
...
A fun fact about generative AI is that researchers at OpenAI created a language processing AI called GPT-3 that can write poetry, stories, and even computer code. In fact, GPT-3 is so good at writing that it has fooled people into thinking its output was written by a human.
(gpt-3.5-turbo) retry
...
One fun fact about generative AI is that it has been used to create a new Rembrandt painting. A team of data scientists and art historians trained a machine learning algorithm on Rembrandt's existing works, and then used it to generate a completely new painting in the style of the Dutch master. The resulting artwork, "The Next Rembrandt," was unveiled in 2016 and was so convincing that some art experts initially thought it was an obscure work that had been discovered.
```

Too high, though, and GPT will just emit nonsense:

```
(gpt-3.5-turbo) set temperature 2
OK
(gpt-3.5-turbo) retry
...
Generative AI systems such as StyleGAN computer programs essentially morph multiple average-per-formed components– rather than situ completed costume area beside time. There are generators solving photos backward-gen generate depicting costumes focusing pointing fire aspect letting content input forming muscles reaching plants including drawings whatever model constituent. ForeignKey Your virtual images think influences know example example TensorFlow
```
(rest of output omitted)

Another useful parameter is `timeout` which controls how long (in seconds) Gptcmd waits for a response from GPT:

```
(gpt-3.5-turbo) set timeout 0.5
OK
(gpt-3.5-turbo) say Hello!
...
Request timed out.
```

The `set` command with no arguments shows all set API parameters:

```
(gpt-3.5-turbo) set
temperature: 2
timeout: 0.5
```

The `unset` command, with an argument, reverts the specified API parameter to its default value. With no argument, it restores all API parameters to default.

### Names
GPT allows mesages to be annotated with the name of their author. If you have access to `gpt-4`, it seems to respond better to these annotations in my experience. The `model` command switches the active GPT model:

```
(gpt-3.5-turbo) model gpt-4
OK
```

The `name` command sets the name to be sent with all future messages of the specified role. Its first argument is the role to which this new name should be applied, and its second is the name to use:

```
(gpt-4) name user Michael
OK
(gpt-4) say Hello!
...
Hello, Michael! How can I help you today?
```

With no arguments, `name` shows currently set names:

```
(gpt-4) name
user: Michael
```

The `unname` command removes a name definition. With a role passed as an argument, it unsets the name definition for that role. With no arguments, it unsets all definitions. However, any previous definitions are unaffected:

```
(gpt-4) view
Michael: Hello!
assistant: Hello, Michael! How can I help you today?
```

Name annotations are useful for providing one- or multi-shot prompts to GPT, in which example user and assistant messages help inform future responses:

```
(gpt-4) system You are a helpful assistant who understands many languages very well, but can only speak Spanish and therefore you always respond in that language.
OK
(gpt-4) name system example_user
OK
(gpt-4) system Hello!
OK
(gpt-4) name system example_assistant
OK
(gpt-4) system ¡Hola! ¿Cómo estás?
OK
(gpt-4) view
system: You are a helpful assistant who understands many languages very well, but can only speak Spanish and therefore you always respond in that language.
example_user: Hello!
example_assistant: ¡Hola! ¿Cómo estás?
(gpt-4) say Qu'est-ce que amazon.com?
...
Amazon.com es una tienda en línea que ofrece una amplia variedad de productos como libros, electrónica, ropa, juguetes y más. Es una de las empresas de comercio electrónico más grandes y populares del mundo.
```

The `rename` command changes the name set on existing messages in the conversation. The command has two required arguments and one optional argument: the role to affect, the range of messages to affect, and (optionally) the name to set (if omitted, the name is cleared). For instance, `rename assistant .` clears the name on all assistant messages in the conversation where a name is set, `rename user 1 Paul` sets the name of the first message to "Paul" if it is a user message, and `rename system 2 5 Mitchell` sets the name of all system messages in the second through fifth to "Mitchell".

### Sticky messages
Messages can be marked "sticky", so deletion, renaming, and similar modifications do not affect them. This is often useful for system messages and example context that you don't wish to delete accidentally. The sticky command takes the range of messages to sticky as an argument:

```
(gpt-3.5-turbo) system You are a Python programmer. Therefore, when responding, you write in Python source code exclusively.
OK
(gpt-3.5-turbo) sticky .
OK
```

Now that the message is sticky, `clear` does not affect it, and its sticky status is indicated by an asterisk:

```
(gpt-3.5-turbo) say Find the nth fibanacci number.
...
Here's a Python function that returns the nth Fibonacci number:
```
```python
def fibonacci(n):
    if n == 0:
        return 0
    elif n == 1:
        return 1
    else:
        return fibonacci(n-1) + fibonacci(n-2)
```
```
You can call this function with the desired value of n, like this:
```
```python
print(fibonacci(10))  # Output: 55
```
```
This will output the nth Fibonacci number. In this case, it's the 10th Fibonacci number, which is 55.
(gpt-3.5-turbo) clear
Delete 2 messages? (y/n)y
OK
(gpt-3.5-turbo) view
*system: You are a Python programmer. Therefore, when responding, you write in Python source code exclusively.
```

Similarly, `pop` is blocked:

```
(gpt-3.5-turbo) pop
That message is sticky; unsticky it first
```

The `unsticky` command makes all sticky messages in the specified range no longer sticky:

```
(gpt-3.5-turbo) unsticky .
OK
(gpt-3.5-turbo) pop
'You are a Python programmer. Therefore, when responding, you write...' deleted
```

### Message threads
Until this point, we have been engaging in a single conversation (or series of conversations) with GPT. However, Gptcmd supports the creation and maintenance of several concurrent GPT conversation "threads".

Gptcmd starts in the "detached thread", a scratch area intended for quick conversation. A new, named conversation thread can be created from the current thread with the `thread` command, which takes a name for the new thread as an argument:

```
(gpt-3.5-turbo) say What is the closed-form formula to find the nth Fibanacci number?
...
The closed-form formula to find the nth Fibonacci number is:

F(n) = [ (1 + √5)ⁿ - (1 - √5)ⁿ ] / [ 2ⁿ √5 ]
(gpt-3.5-turbo) thread induction
Switched to new thread 'induction'
```

The prompt changes to indicate the current thread, and all messages have been copied:

```
induction(gpt-3.5-turbo) view
user: What is the closed-form formula to find the nth Fibanacci number?
assistant: The closed-form formula to find the nth Fibonacci number is:

F(n) = [ (1 + √5)ⁿ - (1 - √5)ⁿ ] / [ 2ⁿ √5 ]
```

The `thread` command with no argument switches back to the detached thread:

```
induction(gpt-3.5-turbo) thread
detached thread
(gpt-3.5-turbo) say Tell me a fun fact about Braille.
...
Louis Braille, the inventor of the Braille system, was blinded in both eyes at the age of three after accidentally stabbing himself in the eye with his father's awl.
```

Passing the name of an existing thread as an argument to `thread` switches to that thread. Once created, threads are completely independent:

```
(gpt-3.5-turbo) last 3
assistant: The closed-form formula to find the nth Fibonacci number is:

F(n) = [ (1 + √5)ⁿ - (1 - √5)ⁿ ] / [ 2ⁿ √5 ]
user: Tell me a fun fact about Braille.
assistant: Louis Braille, the inventor of the Braille system, was blinded in both eyes at the age of three after accidentally stabbing himself in the eye with his father's awl.
(gpt-3.5-turbo) thread induction
Switched to thread 'induction'
induction(gpt-3.5-turbo) last 3
user: What is the closed-form formula to find the nth Fibanacci number?
assistant: The closed-form formula to find the nth Fibonacci number is:

F(n) = [ (1 + √5)ⁿ - (1 - √5)ⁿ ] / [ 2ⁿ √5 ]
```

When running `retry` in a named thread, a new thread is created so that both responses are preserved:

```
induction(gpt-3.5-turbo) say Prove by induction that this formula is equivalent to the recursive definition.
...
To prove that the closed-form formula is equivalent to the recursive definition of the Fibonacci sequence, we can use mathematical induction.

Base case:
When n = 1, the formula gives F(1) = [ (1 + √5) - (1 - √5) ] / [ 2 √5 ] = 1, which is the correct value for the first Fibonacci number according to the recursive definition.
```
(rest of proof omitted)
```
induction(gpt-3.5-turbo) retry
Switched to new thread 'induction2'
...
To prove that the closed-form formula is equivalent to the recursive definition of the Fibonacci sequence, we can use mathematical induction.

Base case:
When n = 1, the recursive definition gives F(1) = 1 and the closed-form formula gives F(1) = [ (1 + √5)¹ - (1 - √5)¹ ] / [ 2¹ √5 ] = 1. Therefore, the base case is true.
```
(rest of proof omitted)

We can continue our conversation from here:

```
induction2(gpt-3.5-turbo) say Write a short explanation of this proof.
...
The proof shows that the closed-form formula for the nth Fibonacci number is equivalent to the recursive definition of the Fibonacci sequence. The proof uses mathematical induction, which is a technique that allows us to prove a statement for all positive integer values of n.

The proof starts by establishing the base case, which is n=1. Then, the proof assumes that the closed-form formula is true for all values of k ≤ n, where n ≥ 1. This is called the inductive hypothesis.

Next, the proof uses the inductive hypothesis to show that the closed-form formula is also true for n+1. This is called the inductive step. The proof shows that by substituting the closed-form formula for F(n) and F(n-1) using the inductive hypothesis, we can derive the closed-form formula for F(n+1).

Since the proof establishes the base case and shows that the inductive hypothesis implies the inductive step, we can conclude that the closed-form formula is true for all positive integer values of n. Therefore, the closed-form formula and the recursive definition of the Fibonacci sequence are equivalent.
```

Or return to the original response before we ran `retry`:

```
induction2(gpt-3.5-turbo) thread induction
Switched to thread 'induction'
```

The `slice` command copies a range of messages to the detached thread, overwriting any existing contents:

```
induction(gpt-3.5-turbo) thread
detached thread
(gpt-3.5-turbo) clear
Delete 4 messages? (y/n)y
OK
(gpt-3.5-turbo) say Write a short description of the NVDA screen reader.
...
NVDA (NonVisual Desktop Access) is a free, open-source screen reader for Windows that allows individuals who are blind or visually impaired to access and navigate their computer. It provides spoken feedback for all on-screen text, including web pages, documents, and applications, as well as keyboard shortcuts and customizable settings. NVDA is compatible with various braille displays and can be used with a variety of languages and speech synthesizers. It is designed to be easy to use and highly customizable, making it a popular choice for many users.
(gpt-3.5-turbo) thread induction2
Switched to thread 'induction2'
induction2(gpt-3.5-turbo) slice 1 2
Selecting 2 messages
First message selected: 'What is the closed-form formula to find the nth...'
Last message selected: 'The closed-form formula to find the nth Fibonacci...'
Unsaved detached messages will be lost.
Confirm slice? (y/n)y
OK
induction2(gpt-3.5-turbo) thread
detached thread
(gpt-3.5-turbo) say Write a C program that implements this formula to print the first 10 Fibanacci numbers.
...
Here's a C program that implements the closed-form formula to print the first 10 Fibonacci numbers:

#include <stdio.h>
#include <math.h>

int main() {
    int n = 10; // number of Fibonacci numbers to print
    int i;
```
(rest of output omitted)

The `threads` command lists the named threads present in this session:

```
(gpt-3.5-turbo) threads
induction2 (6 messages)
induction (4 messages)
(4 detached messages)
```

The `delete` command, with the name of a thread passed as an argument, deletes the specified thread:

```
(gpt-3.5-turbo) delete induction
OK
(gpt-3.5-turbo) threads
induction2 (6 messages)
(4 detached messages)
```

With no argument, `delete` deletes **all** named threads in this session:

```
(gpt-3.5-turbo) delete
Delete 1 thread? (y/n)y
OK
(gpt-3.5-turbo) threads
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
usage: gptcmd [-h] [-t THREAD] [--version] [path]

positional arguments:
  path                  The path to a JSON file of named threads to load on launch

options:
  -h, --help            show this help message and exit
  -t THREAD, --thread THREAD
                        The name of the thread to switch to on launch
  --version             Show version and exit
```
