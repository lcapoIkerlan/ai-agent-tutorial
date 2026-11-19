import pytest

from app import agent
from app.agent import Answer, LLMError, answer_question
from app.indexer import Chunk


class FakeIndex:
    def __init__(self, chunks):
        self.chunks = chunks

    def search(self, query, k=5):
        return self.chunks

    def count(self):
        return len(self.chunks)


class Boom(Exception):
    pass


def fake_completion(calls, content="the answer"):
    def completion(**kwargs):
        calls.append(kwargs)
        msg = type("M", (), {"content": content})()
        return type("R", (), {"choices": [type("C", (), {"message": msg})()]})()

    return completion


def test_empty_index_skips_llm(monkeypatch):
    calls = []
    monkeypatch.setattr(agent.litellm, "completion", fake_completion(calls))
    result = answer_question("hi?", FakeIndex([]), "p/m")
    assert result == Answer(
        "No documentation is loaded. Add files to documents/ and restart the agent.", []
    )
    assert calls == []


@pytest.mark.parametrize("q", ["", "   \n"])
def test_blank_question_skips_llm(monkeypatch, q):
    calls = []
    monkeypatch.setattr(agent.litellm, "completion", fake_completion(calls))
    result = answer_question(q, FakeIndex([Chunk("t", "a.md")]), "p/m")
    assert result == Answer("Please send a question.", [])
    assert calls == []


def test_normal_answer(monkeypatch):
    calls = []
    monkeypatch.setattr(agent.litellm, "completion", fake_completion(calls))
    chunks = [Chunk("alpha text", "a.md"), Chunk("beta text", "b.md"), Chunk("gamma", "a.md")]
    result = answer_question("What is it?", FakeIndex(chunks), "p/m")
    assert result.text == "the answer"
    assert result.sources == ["a.md", "b.md"]
    assert calls[0]["model"] == "p/m"
    system = calls[0]["messages"][0]["content"]
    assert "Answer only from the provided excerpts. If the answer is not in them, say so." in system
    assert all(c.text in system for c in chunks)
    assert "What is it?" in str(calls[0]["messages"])


def test_llm_error(monkeypatch):
    def completion(**kwargs):
        raise Boom("bad key")

    monkeypatch.setattr(agent.litellm, "completion", completion)
    with pytest.raises(LLMError, match="bad key"):
        answer_question("q?", FakeIndex([Chunk("t", "a.md")]), "p/m")
