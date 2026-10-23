# Physical AI Wiki

Student project for Introduction to AI. The project page on aegean.ai describes the task:
compile a library of 30 papers on vision-language-action models into a grounded wiki in the
[Open Knowledge Format (OKF) v0.2](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md),
then ingest one held-out paper and keep the wiki correct.

This repository holds the tools that check your wiki. The course runs the same tools at
grading time, so a clean run here means the mechanical checks will pass.

| Tool | What it checks |
|---|---|
| `okf-validate` | the bundle is valid OKF v0.2 and follows the project rules: sources, citations, index, log and one page per entity |
| `okf-ground` | every quoted sentence is on its cited page and inside its bbox, every table value is inside its bbox, and every bbox matches a highlight in your annotated PDF |
| `okf-diff` | which pages changed between two versions of the wiki, and whether pages the new paper did not touch stayed byte-identical |

The tools only read your bundle. They never call a model and never change a file.

## Install

The tools need Python 3.10 or newer and [uv](https://docs.astral.sh/uv/).

```bash
uv tool install git+https://github.com/pantelis/physical-ai-wiki
```

## Run

```bash
okf-validate wiki
okf-ground wiki
okf-diff wiki --git submission-1 HEAD
okf-diff old-wiki/ wiki/
```

Add `--json` to any command for a report your agent can read. The exit status is 0 when there
are no errors, 1 when there are errors and 2 when the tool could not run.

## Use them from Python

The same checks are a Python package, so your agent can call them as functions and read the
findings directly. Add it to your project with `uv add git+https://github.com/pantelis/physical-ai-wiki`.

```python
from pathlib import Path

import pdfplumber

from paiw_tools.ground import ground
from paiw_tools.locate import find_quote
from paiw_tools.validate import validate

wiki = Path("wiki")
for finding in validate(wiki).findings + ground(wiki).findings:
    print(finding.level, finding.rule, finding.path, finding.message)

with pdfplumber.open(wiki / "papers" / "fei2025.pdf") as pdf:
    spans = find_quote(pdf.pages[0], "yet these results may mask fundamental weaknesses in robustness")
print(spans)  # one [x0, y0, x1, y1] per occurrence, in PDF points from the bottom left
```

`find_quote` matches the same way `okf-ground` does, so a bbox it returns passes the check.

## Use them from Pi

Your agent runs in [Pi](https://github.com/earendil-works/pi). This repository is also a Pi
package with one skill, `okf-checks`, which tells your agent when to run each tool and how to
act on what it reports. Install it in your project:

```bash
pi install --local git:github.com/pantelis/physical-ai-wiki
```

Pi loads skills installed in a project only after you trust the project. In the interactive
terminal it asks you once. A scripted run cannot ask, so it skips the skill unless you pass
`--approve`. `--print` also reads any piped standard input as part of the prompt, so close it
when nothing is piped, or the run waits forever:

```bash
pi --print --approve "Ingest papers/fei2025.pdf into the wiki" < /dev/null
```

## The rules in detail

[`docs/design.md`](docs/design.md) lists every rule the tools check, the bundle layout, how
paths and bbox coordinates are interpreted, and what the tools do not check.

## Develop

```bash
uv sync
uv run pytest
```
