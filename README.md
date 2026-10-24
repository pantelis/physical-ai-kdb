# Physical AI Knowledge DB (kDB)

Student project for Introduction to AI. The project page on aegean.ai describes the task:
compile a library of 30 papers on vision-language-action models into a grounded Knowledge DB
(kDB) in the
[Open Knowledge Format (OKF) v0.2](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md),
then ingest one held-out paper and keep the kDB correct. A kDB is a continuously updated
information source in which every claim points to the sentence or table cell that supports it.
A tool confirms that the evidence is there.

## Grounded answers for mission-critical work

A language model writes fluent, confident text whether or not a source supports it. In a chat
about films a wrong answer costs nothing. Where a document decides what someone does next, the
cost is real: a technician sets the torque value printed in a maintenance manual, and a
pharmacist gives the dose on a drug label. Reactor procedures and motor datasheets are used the
same way. An answer drawn from documents like these is useful only if it can be traced to the
passage that states it, and someone has to check that trace before acting on it.

Two court cases show what happens when nobody checks. In 2023 a federal court in New York
sanctioned two lawyers who filed a brief citing court decisions that ChatGPT had invented
(Mata v. Avianca). In 2024 a Canadian tribunal held Air Canada liable for a refund policy its
website chatbot made up (Moffatt v. Air Canada). Both answers looked authoritative, and nobody
compared them with a source.

Retrieval-augmented generation (RAG) helps by putting relevant passages in front of the model,
but the model can still combine fragments wrongly or cite a passage that does not support its
answer. A citation only tells the reader where to look. We ran into this while building the
reference kDB for this project. One paper prints two result tables side by side, and our
extractor read each printed line as one row, so numbers from one benchmark were filed under
another. Every number was on the cited page, so a check that only asks whether the text is in
the document passed. We found the error when a number looked wrong and someone compared it with
its table, and we then changed the reader to split tables that share a line.

In a kDB, each claim is written once into a page together with its evidence: the paper, the
page, the exact sentence or table cell, and the box on the page where it appears. `okf-ground`
checks that the evidence is where the page says it is, and the highlight in the annotated PDF
lets a person confirm a claim in seconds. Results record their conditions as ontology terms, so
numbers measured under different setups are not compared with each other. When two sources
disagree, the kDB keeps both and records the dispute. Git history and `okf-diff` show what each
new paper changed, and the question history records which version of the kDB each answer used.
If the kDB does not contain an answer, your program should say so; refusals are graded along
with answers.

Audits in regulated industries ask for the same things: a trace from each statement to its
source, a record of what changed and when, and a plain answer when the sources say nothing. The
EU AI Act requires high-risk AI systems to keep records that make their operation traceable.
Many of these documents cannot leave the organization that holds them, for reasons such as
patient privacy, export control or trade secrets, so an agent for them has to run on local
models. The papers in this project are public, so you may also use OpenRouter (see the next
section).

The papers in this library are about robot learning, but nothing in the method depends on that.
With an aircraft's maintenance manuals or a plant's operating procedures in place of the papers,
the same checks apply. In this project you build an agent whose output a tool can verify,
compare it with a RAG baseline on correctness and token use, and teach it to say when the
sources have no answer.

The checks prove that a quoted sentence or value is where its source says it is. They cannot
prove that the sentence supports the claim it is attached to, so a TA reads a sample of claims
at grading time.

This repository holds the tools that check your kDB. The checks come from
[aegean-ai/kdb-tools](https://github.com/aegean-ai/kdb-tools), which other course projects that
build a kDB share. This repository adds the rules and the seed ontology for this project.
Installing it gives you both. The course runs the same tools at grading time, so a clean run
here means the mechanical checks will pass.

## Models and agents you may use

You build the agent yourself, in Python, with Pydantic AI. That agent is what this project is
about, so no other agent may do its work. Commercial agent products and hosted agent services,
such as the ChatGPT, Claude or Gemini apps, NotebookLM or a hosted agent platform, are not
accepted, and neither is a framework that runs its own agent to write the kDB.

The model behind your agent can come from one of three places:

1. A local OpenAI-compatible server with an open-weight model, such as Ollama, llama.cpp, vLLM,
   SGLang or LM Studio.
2. A free model on [OpenRouter](https://openrouter.ai/models), whose model ids end in `:free`.
   Free models are rate limited, so ingest runs slower.
3. A paid model on OpenRouter, with a strict credit limit set on your API key before you start.
   One build of the kDB from the 31 papers took our reference agent about 3.6 million input tokens
   and 0.8 million output tokens, and you will build it many times while you develop.

No other hosted model API is allowed. Keep your OpenRouter key in an environment variable and
never in a file you commit; the starter reads it from the variable named in `kdb.toml`. The papers
in the library are public, which is why OpenRouter is allowed here. With private documents, the
same agent would run on a local model.

## Your tasks, in order

The project page on aegean.ai is the full statement of the task, the rules and the grading. These
are the steps it asks for, arranged in the order that works.

1. Set up. Install the tools (see [Install](#install)), and choose your model as described in
   [Models and agents you may use](#models-and-agents-you-may-use): a local server, a free OpenRouter
   model, or a paid OpenRouter model with a credit limit on your key. Your agent reads the
   `base_url`, the model name and the name of the key's environment variable from `kdb.toml`,
   because we run it against our own server at grading time.
2. Get the library. Download the 30 papers listed on the project page, each at the arXiv version
   it links, and save each as `kdb/papers/<arxiv-id>.pdf`. Keep the paper marked "ingest last"
   aside. Make `kdb/` a git repository.
3. Seed the ontology. Run `okf-seed kdb` once. It writes the robotics, datasets and vla-datasets
   ontologies as `Term` pages. Each term is defined by a quote that the tool highlights in your
   copy of a paper. `okf-validate kdb` and `okf-ground kdb` pass on the result.
4. Build your agent. Start from [`starter/`](starter/README.md), which has the Pydantic AI plumbing,
   and write the harness in Python with Pydantic AI. Use typed tools that read a PDF
   with page positions, find quotes and table cells with `kdb_tools.locate.find_quote`, write
   highlights with `kdb_tools.annotate.highlight`, and write kDB pages. Make the tools reject a
   bad call, such as a quote that is not on the cited page. The model then gets the error and tries
   again. Check the size of every prompt before you send it. A server cuts a prompt longer than
   its context without an error.
5. Write `ingest <pdf>`. It adds one paper to an existing kDB and changes only the pages that
   paper affects. Each model, dataset, benchmark and robot gets one page. Every result states its
   conditions as ontology terms, and every model names its training datasets in `trained_on`. A
   claim that a newer paper disputes stays, with `contested_by` pointing at the new sources. It
   updates `index.md` and appends one entry to `log.md`.
6. Build the kDB from the 30 papers, one `ingest` at a time, committing after each. After every
   paper, run `okf-validate kdb` and `okf-ground kdb`, and have your agent fix what they report.
   Test the incremental update yourself: hold one paper out, ingest it last, and run
   `okf-diff kdb --git <before> HEAD`.
7. Write the question commands. `ask "<question>"` answers from the kDB alone, cites a source
   for every sentence and says so when the kDB does not contain the answer. `--show` displays each
   cited region with its highlight. `history` lists earlier questions, and `ask --save` files an
   answer back into the kDB as an `Analysis` page that passes both checks. Keep the history in a
   SQLite file next to the kDB.
8. Submission 1: your code and command-line program, the kDB built from the 30 papers with its
   ontology, and the annotated PDFs. The paper marked "ingest last" must not be in it.
9. Ingest the held-out paper with one `ingest`. Run `okf-diff` between Submission 1 and the new
   commit, and write a findings report of at most two pages: every page that changed and why,
   every claim the new paper contradicts or supersedes with both sources, and anything you marked
   as contested.
10. Submission 2: the updated kDB, the new annotated PDF and the findings report.
11. The demo. A TA asks your program questions with `ask`, including one that needs several papers
    and one the library cannot answer. The TA looks at the highlights with `--show`, saves an
    answer with `--save` and reads your `history`.

Stretch goals, for credit beyond the required score, are on the project page: standing queries
refreshed on every ingest, extensions to the ontology, and a short write-up of how your agent
reads a paper longer than its context window.

## Where the tools fit

Orange boxes are what you build. Blue boxes come from the course: the papers you download,
the seed ontology and the checks in this repository. The model server is a local server or
OpenRouter, behind an OpenAI-compatible endpoint.

```mermaid
graph TB
    papers["papers/&lt;arxiv-id&gt;.pdf<br/>30 papers, then one more"]
    reader["PDF reader<br/>text with page positions"]
    cli["Command line<br/>ingest · ask · history · ask --save"]
    agent["Agent harness<br/>Pydantic AI, typed tools"]
    llm["Model server<br/>OpenAI-compatible endpoint"]
    kdb["kDB: OKF bundle<br/>pages · ontology/ · index.md · log.md"]
    annotated["annotated/&lt;arxiv-id&gt;.pdf<br/>one highlight per source"]
    history["SQLite history<br/>questions, citations, kDB commit"]
    seed["okf-seed<br/>seed ontology"]
    checks["okf-validate · okf-ground · okf-diff"]

    papers --> reader --> agent
    cli --> agent
    agent <--> llm
    agent -->|"writes pages"| kdb
    agent -->|"writes highlights"| annotated
    agent -->|"stores answers"| history
    seed -->|"Term pages"| kdb
    kdb --> checks
    annotated --> checks
    papers --> checks
    checks -->|"findings to fix"| agent

    classDef yours fill:#e65100,stroke:#bf360c,color:#fff
    classDef given fill:#0277bd,stroke:#01579b,color:#fff
    classDef served fill:#455a64,stroke:#37474f,color:#fff
    classDef data fill:#2e7d32,stroke:#1b5e20,color:#fff
    class reader,cli,agent,history yours
    class papers,seed,checks given
    class llm served
    class kdb,annotated data
```

Green boxes are what you submit, along with your code. The checks read only the kDB, the
annotated PDFs and the papers. They never call a model.

| Tool | What it checks |
|---|---|
| `okf-validate` | the bundle is valid OKF v0.2 and follows the project rules: sources, citations, index, log and one page per entity |
| `okf-ground` | every quoted sentence is on its cited page and inside its bbox, every table value is inside its bbox, and every bbox matches a highlight in your annotated PDF |
| `okf-diff` | which pages changed between two versions of the kDB, and whether pages the new paper did not touch stayed byte-identical |
| `okf-seed` | writes the course's seed ontology into the kDB: one `Ontology` page per ontology (robotics, datasets, and vla-datasets, which extends datasets) and one `Term` page per term, each defined by a quote it finds and highlights in your copy of a library paper |

`okf-validate`, `okf-ground` and `okf-diff` only read your bundle. `okf-seed` writes the ontology pages, their highlights and one log entry. None of the tools calls a model.

## Design choices

### Pluggable rules

The checks are split into a core that every kDB follows and a profile for each project. The core is
[aegean-ai/kdb-tools](https://github.com/aegean-ai/kdb-tools). It handles OKF conformance, sources
and citations, grounding against the PDFs, diffs, and the ontology machinery. This repository is
the `vla` profile. It contains the rules for the page types this project needs and its seed
ontology. The AR4 digital twin project, which builds a kDB of a robot arm's manuals and
datasheets, uses the same core with its own profile.

| Rules | Where they live | What they cover |
|---|---|---|
| `okf.*` | core | frontmatter, `type`, index and log files, as OKF v0.2 defines them |
| `project.index`, `project.log`, `project.generated`, `project.source`, `project.citation`, `project.footnote`, `project.unused-source`, `project.uncited`, `project.aliases`, `project.entity`, `project.contested`, `project.computation` | core | evidence and bookkeeping that any kDB needs |
| `project.ontology`, `project.term`, `project.term-label` | core | layered ontologies and their terms |
| `ground.*`, `diff.*` | core | evidence in the PDFs, and what an update changed |
| `project.result`, `project.condition`, `project.dataset`, `project.trained-on` | `vla` profile | results with their conditions, datasets, training data and model classes |

A profile is a small Python object registered as an entry point in the group
`kdb_tools.profiles`. It names a function that checks one page and a directory of seed specs.
`okf-validate` runs the core rules on every page, followed by the rules of each installed profile.
`okf-seed` writes the seeds of the installed profiles. Both take `--profile` to use one profile
only. Installing this repository installs the core and the `vla` profile together, so the
commands you run are the ones we grade with.

With one core, a fix reaches every project that uses it. If two projects each kept a copy of
the grading tool, a bug fixed in one copy would stay in the other, and students in the two
courses would be graded by different code. The split also lets a project add rules without forking the checker. You can
use the same approach for your own work. Register a profile with extra checks that your agent
runs during ingest, such as a rule that every result page names its trial count. Grading uses
only the course's profile.

### Files in git are the source of truth

The kDB is a directory of markdown files in a git repository, and those files are its source of
truth. Any tool can read them, and git can diff, review and revert them. Grading the incremental
update depends on this: `okf-diff` compares two commits and checks that pages a new paper did not
touch stayed byte-identical. A database or a search index can still help answer questions
quickly, but it is built from the files, it can be discarded and rebuilt at any time, and
nothing is written back from it.

### Evidence is pinned in PDF coordinates

A source names the paper, the page, the exact quote or table value, and a `bbox` in PDF points
with the origin at the bottom-left corner of the page. PDF highlights use that coordinate space,
so a bbox can be compared with your highlight directly. Text extractors measure from the top of
the page. `okf-ground` notices a bbox measured that way and prints the corrected one. A table
value is checked by its position as well as its presence because the same number often appears
in several tables on a page.

### Quotes are matched in drawing order

A PDF stores characters and their drawing positions rather than sentences. Text extractors
reorder lines, so two columns at the same height can come out interleaved. `okf-ground` first
matches a quote against the characters in the order the PDF draws them. It then tries reading
order and finally checks column by column. It rejects a match that jumps across the gap between
columns because words spliced from two columns do not form a sentence in the paper.
`kdb_tools.locate.find_quote` uses the same matcher, so your agent and the checker agree on where
a quote is.

### Conditions name ontology terms

The same word names different things across papers. LIBERO-90 is an evaluation suite of the
LIBERO benchmark and also a set of tasks used as pretraining data. Conditions, dataset properties
and model classes therefore name `Term` pages of an ontology. Those pages have preferred and
alternative labels, with `broader` links in the style of W3C SKOS. Ontologies are layered:
`vla-datasets` extends `datasets`, so a question about pretraining also finds cross-embodiment
pretraining. Every term is defined by a sentence quoted from a library paper and grounded like
any other claim.

### The checks never call a model

Every check is deterministic, so the same bundle gives the same findings on your machine and at
grading time. It runs at no cost and finishes in seconds. Each tool prints a report for people.
With `--json`, it also prints one for your agent. It exits with 0 when there are no errors, 1 when
there are errors and 2 when it could not run. The tools leave one judgment to a person: whether a
cited sentence supports its claim.

### Your agent and our checks are separate

You write the agent that reads papers and writes pages, with Pydantic AI, using a local model or
one on OpenRouter. We own the checks. The bundle format defines the boundary, leaving you
free to build the agent however you like. The checks grade the kDB it produces regardless of how
it was produced. The demo grades the answers your program gives from that kDB.

## Install

The tools need Python 3.11 or newer and [uv](https://docs.astral.sh/uv/).

```bash
uv tool install git+https://github.com/pantelis/physical-ai-kdb
```

## Run

```bash
okf-seed kdb          # once, before the first ingest; needs papers/<arxiv-id>.pdf
okf-validate kdb
okf-ground kdb
okf-diff kdb --git submission-1 HEAD
okf-diff old-kdb/ kdb/
```

Add `--json` to any command for a report your agent can read. The exit status is 0 when there
are no errors, 1 when there are errors and 2 when the tool could not run.

## Use them from Python

The same checks are available as a Python package, so your agent can call them as functions and
read the findings directly. Add it to your project with `uv add git+https://github.com/pantelis/physical-ai-kdb`.

```python
from pathlib import Path

import pdfplumber

from kdb_tools.ground import ground
from kdb_tools.locate import find_quote
from kdb_tools.validate import validate

kdb = Path("kdb")
for finding in validate(kdb).findings + ground(kdb).findings:
    print(finding.level, finding.rule, finding.path, finding.message)

with pdfplumber.open(kdb / "papers" / "fei2025.pdf") as pdf:
    spans = find_quote(pdf.pages[0], "yet these results may mask fundamental weaknesses in robustness")
print(spans)  # one [x0, y0, x1, y1] per occurrence, in PDF points from the bottom left
```

`find_quote` matches text the same way `okf-ground` does, so a bbox it returns passes the check.

To write the highlights into the annotated copy, use `kdb_tools.annotate.highlight`. It finds
each quote on its page and draws one highlight box per line. This shades only the quoted words.
Give the bbox from your source entry when the text appears more than once on the page:

```python
from kdb_tools.annotate import highlight

found = highlight(
    "kdb/papers/fei2025.pdf",
    "kdb/annotated/fei2025.pdf",
    [(3, "97.1", "fei2025-t1-r2-c1", [190.64, 596.07, 207.72, 605.83])],  # page, text, comment, bbox
)
print(found)  # [True]: one flag per mark; False means the text is not on that page
```

## The rules in detail

The [kdb-tools design](https://github.com/aegean-ai/kdb-tools/blob/main/docs/design.md) lists
the rules every kDB follows, the bundle layout, how paths and bbox coordinates are interpreted,
and what the tools do not check. [`docs/design.md`](docs/design.md) lists the rules this
project adds and describes its seed ontology.

## Develop

```bash
uv sync
uv run pytest
```
