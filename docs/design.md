# Tool design

This repository ships four command-line tools, the same checks as a Python package
(`kdb_tools`), and an optional Pi package. Students run the tools themselves, and their agent
calls them as part of every build and ingest. The course runs the same tools at grading time,
so a clean run here means the mechanical checks will pass.

A kDB (Knowledge DB) is a continuously updated, grounded information source. It is stored as an
OKF v0.2 bundle: markdown pages with YAML frontmatter, kept in git.

## Roles

The student's agent, a harness they write with Pydantic AI, reads papers, writes kDB pages and
annotates PDFs. `okf-validate`, `okf-ground` and `okf-diff` do not call a model and do not
write to the bundle; they only check it and report what is wrong. `okf-seed` writes the seed
ontology pages, their highlights and one log entry. The `okf-checks` skill in `pi/skills/` is
for students who also use Pi: it tells Pi when to run each tool and how to act on the result.

Every tool prints a human-readable report by default and a JSON report with `--json`. It
exits with status 0 when there are no errors, 1 when there are errors, and 2 when it could
not run (for example, a missing directory). Warnings never change the exit status.

## Bundle layout

```text
kdb/
  index.md          # lists every concept page
  log.md            # one entry per ingest, newest first
  <concept>.md      # one concept per page, in any subdirectory
  papers/           # the original PDFs, unmodified
  annotated/        # the annotated copies, same file names as papers/
```

Paths follow OKF section 6.2. A path that starts with `/` is relative to the bundle root, and
any other path is relative to the page that contains it. Use the bundle-relative form, for
example `resource: /papers/kim2024.pdf`, so a page can move without breaking its sources. The
annotated copy of a paper is the file with the same name in `annotated/`. That directory can
be changed with `--annotated`.

## Coordinates

A `bbox` is `[x0, y0, x1, y1]` in PDF points, in PDF user space: the origin is the bottom-left
corner of the page and y grows upward. This is the space that PDF annotation rectangles use,
so a highlight written by PdfCraft or pypdf can be compared with a bbox directly. Pages are
numbered from 1.

pdfplumber, PyMuPDF and most text extractors report `top` and `bottom` measured down from the
top of the page. Convert them with `y0 = height - bottom` and `y1 = height - top`. When a bbox
misses its text but the same box flipped top to bottom contains it, `okf-ground` says so and
prints the corrected bbox.

## Sources

A source is either a sentence or a table cell.

| Kind | Required keys |
|---|---|
| sentence | `id`, `resource`, `page`, `quote`, `bbox` |
| table cell | `id`, `resource`, `page`, `table`, `row`, `column`, `value`, `bbox` |

## Findings

Each finding has a rule id, a level (`error` or `warning`), the page path, and a message. Rule
ids that start with `okf.` come from the OKF v0.2 conformance section. Rule ids that start with
`project.` are course rules, stricter than OKF, and listed on the project page.

## okf-validate

Checks the bundle's structure without opening any PDF.

| Rule | Level | Check |
|---|---|---|
| `okf.frontmatter` | error | every non-reserved `.md` file has a parseable YAML frontmatter block |
| `okf.type` | error | every frontmatter block has a non-empty `type` |
| `okf.index` | error | an `index.md` has no frontmatter, except `okf_version` at the bundle root |
| `okf.log` | error | every `##` heading in a `log.md` is an ISO date, `YYYY-MM-DD` |
| `project.index` | error | the bundle root has `index.md`, and every concept page is linked from an `index.md` |
| `project.log` | error | the bundle root has `log.md`, and it has at least one `## YYYY-MM-DD` heading |
| `project.generated` | error | every concept has `generated.by` and an ISO 8601 `generated.at` |
| `project.source` | error | every source is a well-formed sentence or table cell, with a unique `id` on its page and a `resource` that exists. The error names the path it looked for, and when a path without a leading `/` would exist from the bundle root it suggests the `/` form |
| `project.citation` | error | every footnote label in the body is the `id` of a source on the same page |
| `project.footnote` | warning | every cited footnote label has a footnote definition |
| `project.unused-source` | warning | every source is cited at least once |
| `project.uncited` | warning | every sentence of prose carries at least one citation |
| `project.aliases` | error | `aliases` is a list of strings |
| `project.entity` | error | no two pages share a title or alias after normalization; Term pages are checked by `project.term-label` instead |
| `project.contested` | error | `contested_by` maps a source id on the page to a list of source ids that exist in the bundle |
| `project.result` | error | a `Result` page has `conditions` with `task`, `benchmark`, `suite`, `trials` and `embodiment` |
| `project.condition` | error | each of `task`, `benchmark`, `suite`, `embodiment` and, when present, `perturbation` is the path of a Term page under `/ontology/<domain>/` |
| `project.term` | error | a `Term` page lives under `ontology/<domain>/`, has `pref_label`, lists `alt_labels` as strings, and its `broader` entries are Term paths in the same domain with no cycle |
| `project.term-label` | error | within one domain, no two Terms share a preferred or alternative label after normalization; the same label may name Terms in two domains |
| `project.computation` | error | an `Attested Computation` page has `runtime: python` and either a `computation` file that exists or a `# Computation` python block |

## The ontology

Conditions name ontology terms, not words, because the same words mean different things in
different domains: pick-and-place on a robot arm is not pick-and-place in a packing shed. Each
term is one page under `ontology/<domain>/`, with fields modelled on W3C SKOS: `pref_label`,
`alt_labels`, `broader`, and optional `exact_match` links to established vocabularies. Its body
is a scope note, cited like any other prose. A term's domain is the directory after `ontology/`,
so labels are unique within a domain and may repeat across domains.

The seed ontology ships as `src/kdb_tools/seeds/robotics.yaml`. Each term lists its labels,
its `broader` terms, any verified `close_match` or `related_match` identifiers, and one or more
scope sentences, each with the exact quote from a library paper that supports it. `okf-seed`
finds every quote in the bundle's own `papers/<arxiv-id>.pdf`, starting with the page the spec
names, so the bbox matches the copy of the paper the student has. A term whose quote is not
found is reported as `seed.quote` and not written. Running `okf-seed` again rewrites only pages
whose content changed, so it never breaks the byte-identical rule. Write arXiv ids in the spec
in quotes: YAML reads `2306.03310` as a number and drops the trailing zero, which `okf-seed`
reports as `seed.spec`.

Name normalization for `project.entity` lowercases the name, writes π as `pi`, and drops every
character that is not a letter or digit. So `OpenVLA-OFT` and `openvla oft` collide, while
`π0` and `pi-zero` do not, which is why `aliases` exists.

## okf-ground

Opens the PDFs and checks every source against them.

| Rule | Level | Check |
|---|---|---|
| `ground.page` | error | the page exists in the PDF |
| `ground.quote` | error | the quote appears in the page's characters, in content-stream order, after normalizing whitespace, ligatures, quotes, dashes and line-break hyphens |
| `ground.bbox` | error | at least one occurrence of the quote, or of the table-cell value, lies inside the bbox, with 2 points of slack on each side. The error gives the position of the text, and says so when the bbox looks measured from the top of the page |
| `ground.highlight` | error | the annotated copy has a highlight on that page whose rectangle overlaps the bbox with intersection over union of at least 0.5 |

Quotes are matched against the page's characters in the order the PDF draws them, not against
extracted page text. Extractors reorder lines: two columns at the same height come out
interleaved, so a sentence can be on the page and still be missing from its text. The same
matcher is available to agents as `kdb_tools.locate.find_quote(page, text)`, which returns the
bbox of every occurrence on a pdfplumber page, so an agent and the checker agree on where a
quote is.

`kdb_tools.locate.find_quote_lines(page, text)` gives the same matches as one box per line, and
`kdb_tools.annotate.highlight` writes them as a single highlight with one quad per line, so the
highlight covers only the quoted words. Its rectangle is the union of the lines, which is what
`ground.highlight` compares with the bbox.

A quote that appears on the page but outside its bbox fails `ground.bbox`, not `ground.quote`,
so the report says whether the text or the location is wrong.

## okf-diff

Compares two versions of a bundle, given as two directories or as two git revisions of the
repository the bundle lives in (`--git <old> <new>`). It lists every concept page that was
added, removed or changed, and for a changed page whether the body, the frontmatter or both
changed.

| Rule | Level | Check |
|---|---|---|
| `diff.rewrite` | error | a page whose content did not change is byte-identical (no reordered keys or reflowed text) |
| `diff.stamp` | error | a page whose body did not change kept its `generated` stamp |
| `diff.stale-stamp` | warning | a page whose body changed has a new `generated.at` |

It also lists changes to `index.md`, `log.md` and the files under `papers/` and `annotated/`, so
the findings report can be checked against them.

## Not checked here

Whether a cited sentence actually supports the claim attached to it is judged by a TA, not by
these tools. The tools do not run Attested Computations yet.
