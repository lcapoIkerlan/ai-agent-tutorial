from pathlib import Path

import pytest
from starlette.testclient import TestClient

from app import a2a_endpoint
from app.agent import Answer, LLMError
from app.config import ConfigError, Settings

V03 = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "message/send",
    "params": {
        "message": {
            "kind": "message",
            "messageId": "m1",
            "role": "user",
            "parts": [{"kind": "text", "text": "hi"}],
        }
    },
}
V10 = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "SendMessage",
    "params": {
        "message": {"messageId": "m1", "role": "ROLE_USER", "parts": [{"text": "hi"}]}
    },
}


def make_settings(key=None):
    return Settings(
        agent_name="Docs Bot",
        agent_description="Answers from docs",
        llm_model="openai/x",
        llm_api_key="k",
        public_url="http://localhost:8000",
        agent_api_key=key,
        documents_dir=Path("documents"),
        data_dir=Path("data"),
    )


class FakeIndex:
    def count(self):
        return 1


@pytest.fixture(autouse=True)
def fake_answer(monkeypatch):
    monkeypatch.setattr(
        a2a_endpoint, "answer_question", lambda q, i, m: Answer("the answer", ["a.md"])
    )


def client(key=None):
    return TestClient(a2a_endpoint.build_app(make_settings(key), FakeIndex()))


def test_agent_card():
    card = client().get("/.well-known/agent-card.json").json()
    assert card["name"] == "Docs Bot"
    assert card["description"] == "Answers from docs"
    versions = {
        i["protocolVersion"]
        for i in card["supportedInterfaces"]
        if i["protocolBinding"] == "JSONRPC"
    }
    assert versions == {"1.0", "0.3"}


def test_v03_message_send():
    result = client().post("/", json=V03).json()["result"]
    assert result["status"]["state"] == "completed"
    text = result["artifacts"][0]["parts"][0]["text"]
    assert "the answer" in text and "Sources: a.md" in text


def test_v10_send_message():
    resp = client().post("/", json=V10, headers={"A2A-Version": "1.0"}).json()
    assert resp["result"]["task"]["status"]["state"] == "TASK_STATE_COMPLETED"


def test_llm_error_fails_task(monkeypatch):
    def boom(q, i, m):
        raise LLMError("quota")

    monkeypatch.setattr(a2a_endpoint, "answer_question", boom)
    status = client().post("/", json=V03).json()["result"]["status"]
    assert status["state"] == "failed"
    assert "The LLM provider returned an error: quota" in str(status["message"])


def test_auth_required_when_key_set():
    c = client("k")
    for headers in ({}, {"Authorization": "Basic k"}, {"Authorization": "Bearer wrong"}):
        r = c.post("/", json=V03, headers=headers)
        assert (r.status_code, r.text) == (401, "Unauthorized")
    assert c.post("/", json=V03, headers={"Authorization": "bearer k"}).status_code == 200
    assert c.get("/.well-known/agent-card.json").status_code == 200


def test_no_auth_when_no_key():
    assert client().post("/", json=V03).status_code == 200


def test_main_exits_on_config_error(monkeypatch, capsys):
    from app import main

    def bad():
        raise ConfigError("Missing AGENT_NAME in your .env file")

    monkeypatch.setattr(main, "load_settings", bad)
    with pytest.raises(SystemExit) as exc:
        main.main()
    assert exc.value.code == 1
    assert "Configuration error: Missing AGENT_NAME" in capsys.readouterr().err
