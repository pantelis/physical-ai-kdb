"""ingest <pdf>: read one paper and add what it says to your lake.

What the starter does: it registers the PDF in the lake's media table with the RegisterMedia
action, so every row can cite it by its sha256. Then it reads the paper a few pages at a time with
the extraction agent from kdb-tools, whose output is your typed facts. Every fact is a
kdb_tools.agent.Quote, so the agent sends back any quote that is not on the page it names. Last,
it checks the rows you wrote with okf-validate and okf-ground.

What is yours: better instructions, how pages are chunked, table cells, ontology terms, aliases,
contested claims, and write_rows, which turns the facts into rows of the VLA tables.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from kdb_tools import guard
from kdb_tools.actions import Context
from kdb_tools.actions.objects import RegisterMedia
from kdb_tools.agent import Chunk, Quote, extraction_agent, pdf_chunks
from kdb_tools.media import sha256_of
from kdb_tools.tools import Checked, KdbTools
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


@dataclass
class Paper:
    """The paper being ingested, as the lake knows it."""

    pdf: Path
    sha256: str  # its key in kdb.media; every MediaRef that cites the paper names it

    @property
    def arxiv_id(self) -> str:
        return self.pdf.stem  # the library keeps each paper as papers/<arxiv-id>.pdf


@dataclass
class Ingested:
    paper: Paper
    facts: list[Fact]
    rows: list[str]  # what write_rows wrote, each as <table>/<iri>
    checked: Checked = field(default_factory=Checked)  # okf-validate and okf-ground on those rows only


def make_agent(model, root: Path | None = None, settings: dict | None = None) -> Agent[Chunk, ChunkFacts]:
    """The chunk agent. Given the kDB root, it can also call find_quote, find_value, find_cell and check_pages
    from kdb-tools, so it can look a quote up before it answers instead of being sent back."""
    return extraction_agent(model, ChunkFacts, INSTRUCTIONS, root=root, settings=settings)


def extract(agent: Agent[Chunk, ChunkFacts], pdf: Path, pages: list[int], prompt: str) -> ChunkFacts:
    return agent.run_sync(prompt, deps=Chunk(pdf, pages)).output


def register(ctx: Context, pdf: Path, origin: str | None = None) -> Paper:
    """The PDF in kdb.media. Registering the same file again changes nothing."""
    pdf = Path(pdf).absolute()
    RegisterMedia().submit(ctx, {"path": str(pdf), "origin": origin or f"https://arxiv.org/abs/{pdf.stem}"})
    return Paper(pdf, sha256_of(pdf.read_bytes()))


def ingest(ctx: Context, pdf: Path, agent: Agent[Chunk, ChunkFacts], context: int, pages_per_chunk: int = 3,
           origin: str | None = None) -> Ingested:
    paper = register(ctx, pdf, origin)
    facts: list[Fact] = []
    for chunk, prompt in pdf_chunks(paper.pdf, pages_per_chunk):
        guard.check(prompt, context)
        facts += extract(agent, paper.pdf, chunk.pages, prompt).facts
    rows = write_rows(ctx, paper, facts)
    return Ingested(paper, facts, rows, check(ctx, rows))


def check(ctx: Context, rows: list[str]) -> Checked:
    """okf-validate and okf-ground on these rows only, so an error an earlier ingest left does not fail this one.

    Name each row <table>/<iri>: that is the path of every finding on it."""
    return KdbTools(ctx.root, ctx=ctx).check_pages(rows) if rows else Checked()


def write_rows(ctx: Context, paper: Paper, facts: list[Fact]) -> list[str]:
    raise NotImplementedError(
        "write_rows is yours: turn the facts into rows of the VLA tables (papers, models, datasets, trained_on, "
        "results) with the UpsertObjects action. Call UpsertObjects().dry_run(ctx, params) first to see the rows "
        "it would write and what it refuses, then UpsertObjects().submit(ctx, params, plan). Cite evidence as "
        "MediaRefs to paper.sha256 with bboxes from kdb_tools.locate.find_quote, highlight each quote with "
        "kdb_tools.annotate.highlight, and register the highlighted copy with RegisterMedia (annotates=paper.sha256). "
        "Return the rows you wrote, each as <table>/<iri>")
