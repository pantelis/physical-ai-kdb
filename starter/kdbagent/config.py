"""Read the model server from kdb.toml, so the agent runs unchanged against any OpenAI-compatible server.

That can be a local server (Ollama, llama.cpp, vLLM, SGLang, LM Studio) or OpenRouter. An API
key is never written in kdb.toml: name the environment variable that holds it in api_key_env.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider


class ConfigError(ValueError):
    pass


@dataclass
class Config:
    base_url: str
    model: str
    context: int = 32768
    api_key: str = "local"  # local servers ignore it, but the OpenAI client needs one


def load(path: Path = Path("kdb.toml")) -> Config:
    raw = tomllib.loads(Path(path).read_text())
    if "api_key" in raw:
        raise ConfigError("do not write an API key in kdb.toml, where it can be committed; set api_key_env to the "
                          "name of the environment variable that holds it, such as OPENROUTER_API_KEY")
    cfg = Config(**{k: raw[k] for k in ("base_url", "model", "context") if k in raw})
    if "api_key_env" in raw:
        key = os.environ.get(raw["api_key_env"])
        if not key:
            raise ConfigError(f"kdb.toml says the API key is in {raw['api_key_env']}, which is not set")
        cfg.api_key = key
    return cfg


def model_from(cfg: Config) -> OpenAIChatModel:
    return OpenAIChatModel(cfg.model, provider=OpenAIProvider(base_url=cfg.base_url, api_key=cfg.api_key))
