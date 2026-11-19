"""Retrieval agent: fetches relevant excerpts from the index and asks the LLM to answer from them."""

from dataclasses import dataclass

import litellm

from app.indexer import Index

NO_DOCS = "No documentation is loaded. Add files to documents/ and restart the agent."
BLANK = "Please send a question."
SYSTEM_PROMPT = (
    "You are a documentation assistant. "
    "Answer only from the provided excerpts. If the answer is not in them, say so.\n\n"
    "Excerpts:\n{excerpts}"
)


class LLMError(Exception):
    """The LLM provider failed; the message is the provider's reason."""


@dataclass(frozen=True)
class Answer:
    text: str
    sources: list[str]


def answer_question(question: str, index: Index, model: str) -> Answer:
    if index.count() == 0:
        return Answer(NO_DOCS, [])
    if not question.strip():
        return Answer(BLANK, [])
    chunks = index.search(question)
    excerpts = "\n\n".join(f"[{c.source}]\n{c.text}" for c in chunks)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(excerpts=excerpts)},
        {"role": "user", "content": question},
    ]
    try:
        response = litellm.completion(model=model, messages=messages)
        text = response.choices[0].message.content
    except Exception as exc:
        raise LLMError(str(exc)) from exc
    if not text or not text.strip():
        raise LLMError("The model returned an empty response")
    return Answer(text, list(dict.fromkeys(c.source for c in chunks)))
