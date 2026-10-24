"""ask "<question>": answer from the kDB alone, citing a source for every sentence.

What the starter does: an agent with two tools that read the kDB, and an answer whose every
claim must cite source ids that exist on the page it names. What is yours: tools that scale
to hundreds of pages (results, the ontology), printing the citations, --show, --save and the
SQLite history.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kdb_tools import bundle as B
from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelRetry, RunContext


class Claim(BaseModel):
    text: str = Field(description="one sentence of the answer, in your own words")
    page: str = Field(description="the kDB page the evidence is on, such as models/openvla.md")
    source_ids: list[str] = Field(min_length=1, description="ids of sources on that page that support the sentence")


class Answer(BaseModel):
    answerable: bool = Field(description="false when the kDB does not contain the answer")
    claims: list[Claim] = Field(default_factory=list)
    note: str = Field(default="", description="when not answerable, what is missing")


@dataclass
class KDB:
    root: Path


INSTRUCTIONS = (
    "You answer questions using only a knowledge base (kDB) of research pages. Find the pages you need, read them, "
    "and write each sentence of the answer as a claim that names its page and the ids of the sources on that page "
    "that support it. If the kDB does not contain the answer, set answerable to false."
)  # yours to improve


def sources(root: Path, rel: str) -> dict[str, dict] | None:
    path = (root / rel).resolve()
    if not path.is_file() or root.resolve() not in path.parents:
        return None
    page = B.read_page(root.resolve(), path)
    return {s["id"]: s for s in page.sources if isinstance(s, dict) and "id" in s}


def make_agent(model) -> Agent[KDB, Answer]:
    agent = Agent(model, deps_type=KDB, output_type=Answer, instructions=INSTRUCTIONS, retries=2)

    @agent.tool
    def list_pages(ctx: RunContext[KDB]) -> list[dict]:
        """Every page with its type and title. On a large kDB this list is long: replace it with tools that search."""
        return [{"path": p.rel, "type": (p.frontmatter or {}).get("type"), "title": (p.frontmatter or {}).get("title")}
                for p in B.load(ctx.deps.root).concepts]

    @agent.tool
    def read_page(ctx: RunContext[KDB], path: str) -> dict:
        """One page's text and the sources you may cite from it."""
        found = sources(ctx.deps.root, path)
        if found is None:
            raise ModelRetry(f"there is no page {path}; call list_pages")
        page = B.read_page(ctx.deps.root.resolve(), (ctx.deps.root / path).resolve())
        return {"body": page.body, "sources": list(found.values())}

    @agent.output_validator
    def claims_cite_real_sources(ctx: RunContext[KDB], answer: Answer) -> Answer:
        for c in answer.claims:
            found = sources(ctx.deps.root, c.page)
            if found is None:
                raise ModelRetry(f"claim cites page {c.page}, which does not exist")
            unknown = [s for s in c.source_ids if s not in found]
            if unknown:
                raise ModelRetry(f"{c.page} has no sources {unknown}; it has {sorted(found)}")
        return answer

    return agent


def answer(agent: Agent[KDB, Answer], root: Path, question: str) -> Answer:
    return agent.run_sync(question, deps=KDB(root)).output
