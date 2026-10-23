"""okf-seed: write the course's seed ontology into a kDB bundle, grounded in the bundle's own PDFs.

Each term in the seed spec becomes a Term page under ontology/<domain>/<kind>/<slug>.md. Every
scope sentence cites a quote from a library paper. The quote is found in papers/<arxiv-id>.pdf of
the bundle, so the page and bbox match the copy of the paper you have, and it is highlighted in
annotated/<arxiv-id>.pdf. A term whose quote cannot be found is reported and not written. Running
the command again leaves unchanged pages byte-identical.
"""

from __future__ import annotations

import argparse
import datetime as dt
from importlib.resources import files
from pathlib import Path

import pdfplumber
import yaml

from . import bundle as B
from .annotate import highlight
from .ground import Paper, iou
from .locate import find_quote
from .report import Report, fail

TOOL = "okf-seed"
ACTOR = "okf-seed/1"


def term_path(domain: str, kind: str, slug: str) -> str:
    return f"ontology/{domain}/{kind}/{slug}.md"


def locate(pdf: Path, page_hint: int, text: str) -> tuple[int, list[float]] | None:
    """The page (from 1) and bbox of text, looking at the hinted page first."""
    with pdfplumber.open(pdf) as doc:
        order = [page_hint] + [n for n in range(1, len(doc.pages) + 1) if n != page_hint]
        for n in order:
            if 1 <= n <= len(doc.pages):
                spans = find_quote(doc.pages[n - 1], text)
                if spans:
                    return n, spans[0]
    return None


def render(fm: dict, body: str) -> str:
    return "---\n" + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True) + "---\n\n" + body


def write_if_changed(path: Path, fm: dict, body: str) -> bool:
    """Write the page unless only its generated stamp would change."""
    if path.exists():
        try:
            old_fm, old_body = B.split_frontmatter(path.read_text(encoding="utf-8"))
        except B.FrontmatterError:
            old_fm, old_body = None, None
        if old_fm is not None:
            if {k: v for k, v in old_fm.items() if k != "generated"} == {k: v for k, v in fm.items() if k != "generated"} \
                    and old_body.strip() == body.strip():
                return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(fm, body), encoding="utf-8")
    return True


def already_highlighted(annotated: Path, page_no: int, bbox: list[float]) -> bool:
    if not annotated.is_file():
        return False
    paper = Paper(annotated)
    try:
        return page_no <= paper.pages and any(iou(bbox, h) >= 0.99 for h in paper.highlights(page_no))
    finally:
        paper.close()


def seed(root: Path, spec_path: Path | None = None) -> Report:
    report = Report(TOOL)
    spec = yaml.safe_load((spec_path or files("kdb_tools.seeds").joinpath("robotics.yaml")).read_text())
    domain, papers = spec["domain"], spec["papers"]
    numeric = sorted(k for k, v in papers.items() if not isinstance(v, str))
    if numeric:
        report.error("seed.spec", str(spec_path or "robotics.yaml"),
                     f"arXiv ids for {', '.join(numeric)} were read as numbers; quote them, as in '2306.03310'")
        return report
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    written, listed, marks = [], [], {}
    for term in spec["terms"]:
        rel = term_path(domain, term["kind"], term["slug"])
        sources, sentences, ok = [], [], True
        for n, scope in enumerate(term["scope"], 1):
            q = scope["quote"]
            arxiv = papers[q["paper"]]
            pdf = root / "papers" / f"{arxiv}.pdf"
            if not pdf.is_file():
                report.error("seed.paper", rel, f"papers/{arxiv}.pdf is missing; download arXiv {arxiv} and save it under that name")
                ok = False
                break
            found = locate(pdf, q.get("page", 1), q["text"])
            if found is None:
                report.error("seed.quote", rel, f"term {term['slug']}: the quote is not in papers/{arxiv}.pdf: {q['text'][:80]}")
                ok = False
                break
            page_no, bbox = found
            sid = f"seed-{term['slug']}-{n}"
            sources.append({"id": sid, "resource": f"/papers/{arxiv}.pdf", "page": page_no, "quote": q["text"], "bbox": bbox})
            sentences.append(f"{scope['text'].rstrip()}[^{sid}]")
            marks.setdefault(arxiv, []).append((page_no, q["text"], sid, bbox))
        if not ok:
            continue
        fm = {"type": "Term", "title": term["pref_label"], "pref_label": term["pref_label"],
              "alt_labels": term.get("alt_labels", [])}
        if term.get("broader"):
            fm["broader"] = ["/" + term_path(domain, next(t["kind"] for t in spec["terms"] if t["slug"] == b), b)
                             for b in term["broader"]]
        for key in ("close_match", "related_match", "exact_match"):
            if term.get(key):
                fm[key] = term[key]
        fm["generated"] = {"by": ACTOR, "at": now}
        fm["sources"] = sources
        notes = "\n".join(f"[^{s['id']}]: arXiv {Path(s['resource']).stem}, page {s['page']}" for s in sources)
        if write_if_changed(root / rel, fm, " ".join(sentences) + "\n\n" + notes + "\n"):
            written.append(rel)
        listed.append((rel, term["pref_label"]))

    for arxiv, items in marks.items():
        annotated = root / "annotated" / f"{arxiv}.pdf"
        todo = [m for m in items if not already_highlighted(annotated, m[0], m[3])]
        if todo:
            highlight(root / "papers" / f"{arxiv}.pdf", annotated, todo)

    index = root / "ontology" / domain / "index.md"
    lines = [f"# {domain.capitalize()} ontology", ""] + [
        f"* [{label}]({Path(rel).relative_to(f'ontology/{domain}').as_posix()}) - a term" for rel, label in sorted(listed)]
    text = "\n".join(lines) + "\n"
    if not index.exists() or index.read_text() != text:
        index.parent.mkdir(parents=True, exist_ok=True)
        index.write_text(text)
    root_index = root / "index.md"
    link = f"(ontology/{domain}/index.md)"
    if root_index.exists() and link not in root_index.read_text():
        root_index.write_text(root_index.read_text().rstrip("\n") + f"\n* [{domain.capitalize()} ontology]{link} - seed terms\n")
    if written:
        log = root / "log.md"
        heading = f"## {dt.date.today().isoformat()}"
        text = log.read_text().rstrip("\n") if log.exists() else "# Log"
        if heading not in text:
            text += f"\n\n{heading}"
        log.write_text(text + f"\n* okf-seed wrote {len(written)} {domain} terms.\n")
    report.extra.update({"written": written, "terms": len(listed)})
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=TOOL, description=__doc__.splitlines()[0])
    parser.add_argument("bundle", type=Path, help="the bundle root directory")
    parser.add_argument("--spec", type=Path, help="a seed spec; default: the course's robotics seed")
    parser.add_argument("--json", action="store_true", help="print a JSON report")
    args = parser.parse_args(argv)
    if not args.bundle.is_dir():
        return fail(TOOL, f"{args.bundle} is not a directory")
    report = seed(args.bundle, args.spec)
    if not args.json:
        print(f"{report.extra['terms']} terms in place, {len(report.extra['written'])} written")
    report.print(args.json)
    return report.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
