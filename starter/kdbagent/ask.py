"""ask "<question>": answer from the kDB alone, citing a source for every sentence.

What the starter does: the ask agent from kdb-tools, with two tools that read the kDB and an
answer whose every claim must cite source ids that exist on the page it names. What is yours:
tools that scale to hundreds of pages (results, the ontology), printing the citations, --show,
--save and the SQLite history.
"""

from __future__ import annotations

from pathlib import Path

from kdb_tools import agent as A
from pydantic_ai import Agent

INSTRUCTIONS = (
    "You answer questions using only a knowledge base (kDB) of research pages. Find the pages you need, read them, "
    "and write each sentence of the answer as a claim that names its page and the ids of the sources on that page "
    "that support it. If the kDB does not contain the answer, set answerable to false."
)  # yours to improve


def make_agent(model, settings: dict | None = None) -> Agent[A.KDB, A.Answer]:
    """Add your own tools with @agent.tool; list_pages stops fitting the context on a large kDB."""
    return A.ask_agent(model, INSTRUCTIONS, settings=settings)


def answer(agent: Agent[A.KDB, A.Answer], root: Path, question: str) -> A.Answer:
    return A.ask(agent, root, question)
