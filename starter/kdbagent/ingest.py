"""ingest <pdf>: read one paper and add what it says to the kDB.

What the starter does: it reads the paper's pages, sends a few pages at a time to an agent
whose output is typed, and makes the agent retry when a quote is not on the page it names.
What is yours: better instructions, how pages are chunked, table cells, ontology terms,
aliases, contested claims, and writing the kDB pages, index, log and highlights.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pdfplumber
from kdb_tools.agent import toolset
from kdb_tools.locate import find_quote
from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelRetry, RunContext

from . import guard
from .config import Config, model_from


class Fact(BaseModel):
    entity: str = Field(description="the model, dataset or benchmark the sentence is about, named as the paper names it")
    kind: Literal["model", "dataset", "benchmark"]
    sentence: str = Field(description="one sentence in your own words that the quote supports")
    quote: str = Field(description="one sentence copied word for word from the page")
    page: int = Field(description="the page the quote is on, counted from 1")


class ChunkFacts(BaseModel):
    facts: list[Fact] = Field(default_factory=list)


@dataclass
class Chunk:
    pdf: Path
    pages: list[int]


INSTRUCTIONS = (
    "You read pages of a research paper about vision-language-action robot models and return facts about the "
    "models, datasets and benchmarks it describes. Every quote must be one sentence copied word for word from the "
    "page you name."
)  # yours to improve


def make_agent(model, root: Path | None = None) -> Agent[Chunk, ChunkFacts]:
    """The chunk agent. Given the kDB root, it can also call find_quote, find_value and check_pages
    from kdb-tools, so it can look a quote up before it answers instead of being sent back."""
    agent = Agent(model, deps_type=Chunk, output_type=ChunkFacts, instructions=INSTRUCTIONS, retries=2,
                  toolsets=[toolset(root)] if root is not None else [])

    @agent.output_validator
    def quotes_are_on_their_pages(ctx: RunContext[Chunk], out: ChunkFacts) -> ChunkFacts:
        problems = []
        with pdfplumber.open(ctx.deps.pdf) as doc:
            for f in out.facts:
                if f.page not in ctx.deps.pages or not find_quote(doc.pages[f.page - 1], f.quote):
                    problems.append(f"page {f.page}: {f.quote!r}")
        if problems:
            raise ModelRetry("These quotes are not on the pages you named. Fix or drop them and return all facts "
                             "again:\n" + "\n".join(problems))
        return out

    return agent


def extract(agent: Agent[Chunk, ChunkFacts], pdf: Path, pages: list[int], prompt: str) -> ChunkFacts:
    return agent.run_sync(prompt, deps=Chunk(pdf, pages)).output


def ingest(root: Path, pdf: Path, cfg: Config, pages_per_chunk: int = 3) -> list[Fact]:
    agent = make_agent(model_from(cfg), root)
    with pdfplumber.open(pdf) as doc:
        texts = [p.extract_text() or "" for p in doc.pages]
    facts: list[Fact] = []
    for start in range(0, len(texts), pages_per_chunk):
        pages = list(range(start + 1, min(start + pages_per_chunk, len(texts)) + 1))
        prompt = "\n".join(f"=== page {p} ===\n{texts[p - 1]}" for p in pages)
        guard.check(prompt, cfg.context)
        facts += extract(agent, pdf, pages, prompt).facts
    write_pages(root, pdf.stem, facts)
    return facts


def write_pages(root: Path, paper: str, facts: list[Fact]) -> None:
    # When you write this, check the pages you wrote with kdb_tools.validate.validate(root, pages=...) and
    # kdb_tools.ground.ground(root, pages=...), so an error an earlier ingest left does not fail this one.
    raise NotImplementedError("writing kDB pages is yours: one page per entity, sources with bboxes from "
                              "kdb_tools.locate.find_quote, highlights with kdb_tools.annotate.highlight, "
                              "index.md and log.md, and pages the paper does not touch left byte-identical")
