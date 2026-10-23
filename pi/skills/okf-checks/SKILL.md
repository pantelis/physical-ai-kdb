---
name: okf-checks
description: Check the Physical AI kDB bundle with okf-validate, okf-ground and okf-diff, and fix what they report. Use after writing or editing kDB pages, after annotating a PDF, and before finishing any build or ingest.
---

# OKF checks

You build and maintain a kDB bundle in OKF v0.2. Three tools check it. They never change the
bundle; you fix what they report. Run them from the bundle's repository. The bundle root is the
directory that holds `index.md`, `log.md`, `papers/` and `annotated/`; below it is `kdb/`.

| Tool | What it checks | Opens PDFs |
|---|---|---|
| `okf-validate kdb --json` | frontmatter, sources, citations, index, log, entity names | no |
| `okf-ground kdb --json` | every quote and table value against its PDF page and bbox, and every bbox against a highlight in `annotated/` | yes |
| `okf-diff kdb --git <old> <new> --json` | which pages changed between two commits, and whether their `generated` stamps are right | no |

If the commands are not found, install them once with
`uv tool install git+https://github.com/pantelis/physical-ai-kdb`.

## When to run them

1. After you write or edit pages, run `okf-validate`. It is fast, so run it often.
2. After you annotate a PDF or add sources, run `okf-ground`.
3. Before you finish a build or an `ingest`, run both and repeat until both report 0 errors.
4. After you commit an `ingest`, run `okf-diff kdb --git HEAD~1 HEAD --json` and use its
   lists of added, changed and removed pages in the `log.md` entry and the findings report.

## Reading a report

Each report is JSON with `ok`, `errors`, `warnings` and `findings`. Each finding has `rule`,
`level`, `path`, `message` and, for a source, `source_id`. Exit status 0 means no errors, 1
means errors, and 2 means the tool could not run.

Fix errors before warnings. Fix one page at a time and rerun the tool, because one cause
often produces several findings.

| Rule | Usual fix |
|---|---|
| `ground.quote` | copy the sentence word for word from the PDF page; do not paraphrase inside `quote` |
| `ground.bbox` | recompute the bbox from the text's position on the page, in PDF points with the origin at the bottom left; if the message prints a corrected bbox, use it |
| `project.source` (resource) | write the path from the bundle root with a leading `/`, such as `/papers/fei2025.pdf`; never copy or move the PDF |
| `project.log` | put each log entry under a `## YYYY-MM-DD` heading with today's date |
| `ground.highlight` | write a highlight with the same rectangle into the copy in `annotated/` |
| `project.citation` | make the footnote label equal to a source `id` on the same page |
| `project.entity` | merge the two pages into one and put the other names in `aliases` |
| `project.contested` | point `contested_by` from the older source id to the newer source ids |
| `diff.rewrite`, `diff.stamp` | restore the page from the previous commit; a page the new paper does not affect stays byte-identical |

Never delete a source or a claim to make a check pass. If evidence does not check out, find
the right sentence or table cell, or mark the claim as not supported in the findings report.
