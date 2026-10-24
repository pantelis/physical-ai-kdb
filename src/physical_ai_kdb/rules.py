"""The VLA profile's page rules: results with conditions, datasets, training data and model classes.

Each condition, collection method, role and model class is the path of a Term page. Collection
methods and roles come from the datasets ontology or one that extends it.
"""

from __future__ import annotations

from kdb_tools import bundle as B
from kdb_tools import validate as V
from kdb_tools.report import Report

RESULT_CONDITIONS = ("task", "benchmark", "suite", "trials", "embodiment")
TERM_CONDITIONS = ("task", "benchmark", "suite", "embodiment", "perturbation")
DATASETS = "datasets"  # the general dataset ontology; VLA dataset ontologies extend it


def check_page(b: B.Bundle, page: B.Page, report: Report) -> None:
    fm = page.frontmatter
    if fm.get("type") == "Result":
        cond = fm.get("conditions")
        missing = [k for k in RESULT_CONDITIONS if not isinstance(cond, dict) or cond.get(k) in (None, "")]
        if missing:
            report.error("project.result", page.rel, f"a Result needs conditions with {', '.join(missing)}")
        for key in TERM_CONDITIONS:
            value = cond.get(key) if isinstance(cond, dict) else None
            if value in (None, ""):
                continue
            target = V.term_at(b, page, value)
            if target is None:
                report.error("project.condition", page.rel,
                             f"condition {key} is '{value}'; it must be the path of a Term page under /ontology/<domain>/")

    ancestors = V.ancestors(b)
    if fm.get("model_class") is not None and V.term_at(b, page, fm["model_class"]) is None:
        report.error("project.condition", page.rel, f"model_class is '{fm['model_class']}'; it must be the path of a Term page")

    if fm.get("type") == "Dataset":
        collection = fm.get("collection")
        if not isinstance(collection, list) or not collection:
            report.error("project.dataset", page.rel, "a Dataset needs collection: a list of collection-method terms")
            collection = []
        for value in collection:
            target = V.term_at(b, page, value)
            if target is None:
                report.error("project.dataset", page.rel, f"collection '{value}' is not a Term page")
            elif not V.in_family(ancestors, V.term_domain(target.rel), DATASETS):
                report.error("project.dataset", page.rel,
                             f"collection '{value}' is not a term of the {DATASETS} ontology or one that extends it")
        for key in ("embodiments", "tasks", "modalities"):
            for value in fm.get(key) or []:
                if V.term_at(b, page, value) is None:
                    report.error("project.dataset", page.rel, f"{key} entry '{value}' is not a Term page")

    if "trained_on" in fm:
        entries = fm["trained_on"]
        if not isinstance(entries, list):
            report.error("project.trained-on", page.rel, "trained_on is a list of {dataset, role, source} entries")
            entries = []
        for entry in entries:
            if not isinstance(entry, dict) or not all(k in entry for k in ("dataset", "role", "source")):
                report.error("project.trained-on", page.rel, "each trained_on entry has dataset, role and source")
                continue
            path = B.resolve(b.root, page.rel, entry["dataset"]) if isinstance(entry["dataset"], str) else None
            target = next((q for q in b.concepts if path is not None and q.path.resolve() == path), None)
            if target is None or (target.frontmatter or {}).get("type") != "Dataset":
                report.error("project.trained-on", page.rel, f"dataset '{entry['dataset']}' is not a Dataset page")
            role = V.term_at(b, page, entry["role"])
            if role is None or not V.in_family(ancestors, V.term_domain(role.rel), DATASETS):
                report.error("project.trained-on", page.rel,
                             f"role '{entry['role']}' is not a term of the {DATASETS} ontology or one that extends it")
            if entry["source"] not in page.source_ids:
                report.error("project.trained-on", page.rel, f"source '{entry['source']}' is not a source id on this page",
                             str(entry["source"]))
