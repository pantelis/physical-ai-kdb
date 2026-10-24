"""Read the model server from kdb.toml, so the agent runs unchanged against any OpenAI-compatible server."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider


@dataclass
class Config:
    base_url: str
    model: str
    context: int = 32768
    api_key: str = "local"  # local servers ignore it, but the OpenAI client needs one


def load(path: Path = Path("kdb.toml")) -> Config:
    raw = tomllib.loads(Path(path).read_text())
    return Config(**{k: raw[k] for k in ("base_url", "model", "context", "api_key") if k in raw})


def model_from(cfg: Config) -> OpenAIChatModel:
    return OpenAIChatModel(cfg.model, provider=OpenAIProvider(base_url=cfg.base_url, api_key=cfg.api_key))
