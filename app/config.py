import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Settings:
    agent_name: str
    agent_description: str
    llm_model: str
    llm_api_key: str | None
    public_url: str
    agent_api_key: str | None
    documents_dir: Path
    data_dir: Path


NEEDS_KEY = {"anthropic", "openai", "gemini"}  # others (e.g. on-prem) may not need a key


def _require(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ConfigError(f"Missing {name} in your .env file")
    return value


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if env is None else env
    name = _require(env, "AGENT_NAME")
    description = _require(env, "AGENT_DESCRIPTION")
    model = _require(env, "LLM_MODEL")
    if "/" not in model:
        raise ConfigError(
            "LLM_MODEL must look like provider/model, e.g. anthropic/claude-sonnet-5-5"
        )
    if model.split("/", 1)[0] in NEEDS_KEY:
        _require(env, "LLM_API_KEY")
    return Settings(
        agent_name=name,
        agent_description=description,
        llm_model=model,
        llm_api_key=env.get("LLM_API_KEY", "").strip() or None,
        public_url=env.get("PUBLIC_URL", "").strip().rstrip("/") or "http://localhost:8000",
        agent_api_key=env.get("AGENT_API_KEY", "").strip() or None,
        documents_dir=Path(env.get("DOCUMENTS_DIR") or "documents"),
        data_dir=Path(env.get("DATA_DIR") or "data"),
    )
