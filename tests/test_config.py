import pytest

from app.config import ConfigError, load_settings

BASE = {
    "AGENT_NAME": "Bot",
    "AGENT_DESCRIPTION": "Answers questions",
    "LLM_MODEL": "anthropic/claude-sonnet-5-5",
    "LLM_API_KEY": "k",
}


def test_valid_env_defaults():
    s = load_settings(BASE)
    assert s.agent_name == "Bot"
    assert s.public_url == "http://localhost:8000"
    assert s.agent_api_key is None
    assert str(s.documents_dir) == "documents"
    assert str(s.data_dir) == "data"


@pytest.mark.parametrize("var", ["AGENT_NAME", "AGENT_DESCRIPTION", "LLM_MODEL"])
def test_missing_required(var):
    env = {k: v for k, v in BASE.items() if k != var}
    with pytest.raises(ConfigError) as e:
        load_settings(env)
    assert str(e.value) == f"Missing {var} in your .env file"


@pytest.mark.parametrize("model", ["anthropic/x", "openai/x", "gemini/x"])
def test_missing_provider_key(model):
    env = {**BASE, "LLM_MODEL": model}
    env.pop("LLM_API_KEY")
    with pytest.raises(ConfigError) as e:
        load_settings(env)
    assert str(e.value) == "Missing LLM_API_KEY in your .env file"


def test_unknown_provider_ok():
    env = {**BASE, "LLM_MODEL": "ollama/llama3"}
    env.pop("LLM_API_KEY")
    assert load_settings(env).llm_model == "ollama/llama3"


def test_model_without_slash():
    with pytest.raises(ConfigError) as e:
        load_settings({**BASE, "LLM_MODEL": "claude"})
    assert str(e.value) == "LLM_MODEL must look like provider/model, e.g. anthropic/claude-sonnet-5-5"


def test_public_url_trailing_slash():
    assert load_settings({**BASE, "PUBLIC_URL": "http://x:9/"}).public_url == "http://x:9"


def test_empty_api_key_is_none():
    assert load_settings({**BASE, "AGENT_API_KEY": ""}).agent_api_key is None
