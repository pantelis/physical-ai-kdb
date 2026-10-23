# Physical AI kDB

Student project for Introduction to AI. The project page on aegean.ai describes the task:
compile a library of 30 papers on vision-language-action models into a grounded kDB in the
[Open Knowledge Format (OKF) v0.2](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md),
then ingest one held-out paper and keep the kDB correct.

This repository holds the tools that check your kDB. The course runs the same tools at
grading time, so a clean run here means the mechanical checks will pass.

| Tool | What it checks |
|---|---|
| `okf-validate` | the bundle is valid OKF v0.2 and follows the project rules: sources, citations, index, log and one page per entity |
| `okf-ground` | every quoted sentence is on its cited page and inside its bbox, every table value is inside its bbox, and every bbox matches a highlight in your annotated PDF |
| `okf-diff` | which pages changed between two versions of the kDB, and whether pages the new paper did not touch stayed byte-identical |
| `okf-seed` | writes the course's seed ontology into the kDB: one `Term` page per term, each defined by a quote it finds and highlights in your copy of a library paper |

`okf-validate`, `okf-ground` and `okf-diff` only read your bundle. `okf-seed` writes the ontology pages, their highlights and one log entry. None of the tools calls a model.

## Install

The tools need Python 3.10 or newer and [uv](https://docs.astral.sh/uv/).

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

The same checks are a Python package, so your agent can call them as functions and read the
findings directly. Add it to your project with `uv add git+https://github.com/pantelis/physical-ai-kdb`.

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

`find_quote` matches the same way `okf-ground` does, so a bbox it returns passes the check.

To write the highlights into the annotated copy, use `kdb_tools.annotate.highlight`. It finds
each quote on its page and draws one highlight box per line, so only the quoted words are
shaded. Give the bbox from your source entry when the text appears more than once on the page:

```python
from kdb_tools.annotate import highlight

found = highlight(
    "kdb/papers/fei2025.pdf",
    "kdb/annotated/fei2025.pdf",
    [(3, "97.1", "fei2025-t1-r2-c1", [190.64, 596.07, 207.72, 605.83])],  # page, text, comment, bbox
)
print(found)  # [True]: one flag per mark; False means the text is not on that page
```

## Use them from Pi

If you also use [Pi](https://github.com/earendil-works/pi), this repository is a Pi package
with one skill, `okf-checks`, which tells an agent when to run each tool and how to act on what
it reports. Install it in your project:

```bash
pi install --local git:github.com/pantelis/physical-ai-kdb
```

Pi loads skills installed in a project only after you trust the project. In the interactive
terminal it asks you once. A scripted run cannot ask, so it skips the skill unless you pass
`--approve`. `--print` also reads any piped standard input as part of the prompt, so close it
when nothing is piped, or the run waits forever:

```bash
pi --print --approve "Ingest papers/fei2025.pdf into the kDB" < /dev/null
```

## The rules in detail

[`docs/design.md`](docs/design.md) lists every rule the tools check, the bundle layout, how
paths and bbox coordinates are interpreted, and what the tools do not check.

## Develop

```bash
uv sync
uv run pytest
```
