"""ingest <pdf>: read one paper and add what it says to the kDB.

What the starter does: it reads the paper a few pages at a time with the extraction agent from
kdb-tools, whose output is your typed facts. Every fact is a kdb_tools.agent.Quote, so the agent
sends back any quote that is not on the page it names. What is yours: better instructions, how
pages are chunked, table cells, ontology terms, aliases, contested claims, and writing the kDB
pages, index, log and highlights.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from kdb_tools import guard
from kdb_tools.agent import Chunk, Quote, extraction_agent, pdf_chunks
from kdb_tools.config import Config, model_from, settings_from
from pydantic import BaseModel, Field
from pydantic_ai import Agent


class Fact(Quote):
    entity: str = Field(description="the model, dataset or benchmark the sentence is about, named as the paper names it")
    kind: Literal["model", "dataset", "benchmark"]
    sentence: str = Field(description="one sentence in your own words that the quote supports")


class ChunkFacts(BaseModel):
    facts: list[Fact] = Field(default_factory=list)


INSTRUCTIONS = (
    "You read pages of a research paper about vision-language-action robot models and return facts about the "
    "models, datasets and benchmarks it describes. Every quote must be one sentence copied word for word from the "
    "page you name."
)  # yours to improve


def make_agent(model, root: Path | None = None, settings: dict | None = None) -> Agent[Chunk, ChunkFacts]:
    """The chunk agent. Given the kDB root, it can also call find_quote, find_value, find_cell and check_pages
    from kdb-tools, so it can look a quote up before it answers instead of being sent back."""
    return extraction_agent(model, ChunkFacts, INSTRUCTIONS, root=root, settings=settings)


def extract(agent: Agent[Chunk, ChunkFacts], pdf: Path, pages: list[int], prompt: str) -> ChunkFacts:
    return agent.run_sync(prompt, deps=Chunk(pdf, pages)).output


def ingest(root: Path, pdf: Path, cfg: Config, pages_per_chunk: int = 3) -> list[Fact]:
    agent = make_agent(model_from(cfg), root, settings_from(cfg))
    facts: list[Fact] = []
    for chunk, prompt in pdf_chunks(pdf, pages_per_chunk):
        guard.check(prompt, cfg.context)
        facts += extract(agent, pdf, chunk.pages, prompt).facts
    write_pages(root, pdf.stem, facts)
    return facts


def write_pages(root: Path, paper: str, facts: list[Fact]) -> None:
    # When you write this, check the pages you wrote with kdb_tools.validate.validate(root, pages=...) and
    # kdb_tools.ground.ground(root, pages=...), so an error an earlier ingest left does not fail this one.
    raise NotImplementedError("writing kDB pages is yours: one page per entity, sources with bboxes from "
                              "kdb_tools.locate.find_quote, highlights with kdb_tools.annotate.highlight, "
                              "index.md and log.md, and pages the paper does not touch left byte-identical")
