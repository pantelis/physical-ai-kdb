"""ask "<question>": answer from your lake alone, citing evidence for every sentence.

What the starter does: an agent that reads the rows of the VLA tables with three tools from
kdb-tools (list_classes, query_objects and get_object), and an answer whose every claim names a
row and the entries of that row's evidence that support it. The validator sends back a claim
whose row or evidence entry does not exist. The agent cannot write: it has no action tools.

What is yours: better instructions, tools that search (by condition term, by benchmark, or with
SQL over the tables), printing the citations, --show, --save and the SQLite history.
"""

from __future__ import annotations

import functools

from kdb_tools.actions import Context
from kdb_tools.tools import KdbTools, ToolInputError
from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelRetry, RunContext

INSTRUCTIONS = (
    "You answer questions using only a lake of rows about vision-language-action robot models: papers, models, "
    "datasets, training links and results. List the classes, query the rows you need, and write each sentence of "
    "the answer as a claim that names one row by its iri and the indexes of the entries of its evidence that "
    "support it. If the rows do not contain the answer, set answerable to false."
)  # yours to improve


class Claim(BaseModel):
    text: str = Field(description="one sentence of the answer, in your own words")
    object: str = Field(description="the iri of the row the evidence is on")
    evidence: list[int] = Field(min_length=1, description="indexes into that row's evidence list, counted from 0")


class Answer(BaseModel):
    answerable: bool = Field(description="false when the rows do not contain the answer")
    claims: list[Claim] = Field(default_factory=list)
    note: str = Field(default="", description="when not answerable, what is missing")


def _retry(fn):
    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ToolInputError as e:  # a call the model should correct: it gets the message
            raise ModelRetry(str(e)) from e
    return wrapped


def make_agent(model, settings: dict | None = None, retries: int = 2) -> Agent[KdbTools, Answer]:
    """Add your own tools with @agent.tool; query_objects returns at most 50 rows unless asked for more."""
    agent = Agent(model, deps_type=KdbTools, output_type=Answer, instructions=INSTRUCTIONS, retries=retries,
                  model_settings=settings or None)

    @agent.tool
    @_retry
    def list_classes(ctx: RunContext[KdbTools]) -> list[dict]:
        """Every class with its status and the table that holds its rows."""
        return ctx.deps.list_classes()

    @agent.tool
    @_retry
    def query_objects(ctx: RunContext[KdbTools], class_iri: str, where: dict[str, str] | None = None,
                      limit: int = 50) -> list[dict]:
        """Rows of a class's table. where maps column names to values the column must equal, compared as text."""
        return ctx.deps.query_objects(class_iri, where, limit)

    @agent.tool
    @_retry
    def get_object(ctx: RunContext[KdbTools], iri: str) -> dict | None:
        """The row with this iri, from whichever class's table holds it, or null."""
        return ctx.deps.get_object(iri)

    @agent.output_validator
    def claims_cite_real_evidence(ctx: RunContext[KdbTools], answer: Answer) -> Answer:
        for c in answer.claims:
            row = ctx.deps.get_object(c.object)
            if row is None:
                raise ModelRetry(f"claim cites the row {c.object}, which does not exist")
            entries = row.get("evidence") or []
            unknown = [f"evidence[{i}]" for i in c.evidence if not 0 <= i < len(entries)]
            if unknown:
                raise ModelRetry(f"{c.object} has no {', '.join(unknown)}; it has {len(entries)} evidence entries")
        return answer

    return agent


def answer(agent: Agent[KdbTools, Answer], ctx: Context, question: str) -> Answer:
    return agent.run_sync(question, deps=KdbTools(ctx.root, ctx=ctx)).output
