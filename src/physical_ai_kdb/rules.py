"""The VLA profile's row rules: results with conditions, datasets, training links, model classes,
contested claims, computations, names and IRIs.

okf-validate runs check_rows once when it has a lake. The rows are those of the tables the VLA
classes bind; a column is read by the property IRI it maps to, so a renamed column still counts.
Each condition, collection method, role and model class is the IRI of a Term page. Collection
methods and roles come from the datasets ontology or one that extends it; conditions and model
classes from the robotics ontology or one that extends it. A contested claim and each statement
that disputes it is <row IRI>#evidence/<index>, an entry of a row's evidence list counted from 0. A
computation's inputs are <row IRI>#<column>. A finding's path is <table>/<row iri>.
A malformed row is a finding, never an exception.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from functools import cache
from importlib.resources import files

import yaml
from kdb_tools import onto as O
from kdb_tools import validate as V
from kdb_tools.report import Report
from kdb_tools.seed import CORE_SEEDS, TYPE_FOLDERS

VLA = "https://kdb.aegean.ai/vla/"
CORE = "https://kdb.aegean.ai/core/"
RESULT_CONDITIONS = ("task", "benchmark", "suite", "trials", "embodiment")
TERM_CONDITIONS = ("task", "benchmark", "suite", "embodiment", "perturbation")
DATASETS = "datasets"  # the general dataset ontology; VLA dataset ontologies extend it
ROBOTICS = "robotics"  # the ontology of tasks, benchmarks, robots and model classes
TRAINED_ON = ("model", "dataset", "role", "evidence")
EVIDENCE_FORM = "<row IRI>#evidence/<index>"
INPUT_FORM = "<row IRI>#<column>"
EVIDENCE_REF = re.compile(r"(?P<iri>.+)#evidence/(?P<index>[0-9]+)")


def vla(slug: str) -> str:
    return f"{VLA}properties/{slug}"


def core(slug: str) -> str:
    return f"{CORE}properties/{slug}"


def klass(slug: str) -> str:
    return f"{VLA}classes/{slug}"


@cache
def seeded_types() -> frozenset[str]:
    """The IRIs of the type pages the core and VLA seeds write; any other type is one a team added."""
    paths = [CORE_SEEDS / "core.yaml"] + [f for f in (files(__package__) / "seeds").iterdir() if f.name.endswith(".yaml")]
    out = set()
    for path in paths:
        spec = yaml.safe_load(path.read_text())
        base = spec.get("base_iri")
        for folder, _, _ in TYPE_FOLDERS if base else ():
            out |= {f"{base}{folder}/{entry['slug']}" for entry in spec.get(folder, [])}
    return frozenset(out)


def table_exists(lake, table: str) -> bool:
    return lake.con.execute("SELECT count(*) FROM information_schema.tables WHERE table_catalog = 'lake' "
                            "AND table_schema = 'main' AND table_name = ?", [table]).fetchone()[0] > 0


def read_rows(lake, k: O.Klass | None) -> tuple[str, list[dict]]:
    """The class's table and its rows keyed by property IRI (iri, type and team keep their names).

    A class with no binding or no table has no rows."""
    if k is None or k.binding is None or not table_exists(lake, k.binding.table):
        return "", []
    table = k.binding.table
    cur = lake.con.execute('SELECT * FROM "' + table.replace('"', '""') + '"')
    keys = [k.binding.columns.get(d[0], d[0]) for d in cur.description]
    return table, [dict(zip(keys, r)) for r in cur.fetchall()]


def rows_of(o: O.Ontology, lake, slug: str) -> tuple[str, list[dict]]:
    return read_rows(lake, o.classes.get(klass(slug)))


def where(table: str, row: dict) -> str:
    return f"{table}/{row.get('iri')}"


def term_rel(o: O.Ontology, value) -> str | None:
    """The page of the Term whose IRI is value, or None."""
    return o.terms.get(value) if isinstance(value, str) else None


def in_family(o: O.Ontology, rel: str, root: str) -> bool:
    return V.in_family(o.ancestors, V.term_domain(rel), root)


def media_refs(value) -> list:
    """The entries of a media_ref_list value, which the lake returns as JSON text; [] for anything else."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    return value if isinstance(value, list) else []


def check_term(o: O.Ontology, report: Report, path: str, what: str, value, hint: str = "") -> None:
    """project.condition: value is the IRI of a Term of the robotics ontology or one that extends it."""
    rel = term_rel(o, value)
    if rel is None:
        report.error("project.condition", path, f"{what} is '{value}'; it must be the IRI of a Term page{hint}")
    elif not in_family(o, rel, ROBOTICS):
        report.error("project.condition", path,
                     f"{what} is '{value}'; it is not a term of the {ROBOTICS} ontology or one that extends it")


def missing_conditions(row: dict) -> list[str]:
    """The conditions a result row lacks. Trials may be empty only when trials_reported is false."""
    def absent(c: str) -> bool:
        if c == "trials":
            return row.get(vla("trials")) is None and row.get(vla("trials_reported")) is not False
        return row.get(vla(c)) in (None, "")
    return [c for c in RESULT_CONDITIONS if absent(c)]


def check_results(o: O.Ontology, lake, report: Report) -> None:
    table, rows = rows_of(o, lake, "result")
    for row in rows:
        path = where(table, row)
        if missing := missing_conditions(row):
            report.error("project.result", path, f"a Result needs conditions with {', '.join(missing)}")
        for key in TERM_CONDITIONS:
            if row.get(vla(key)) not in (None, ""):
                check_term(o, report, path, f"condition {key}", row[vla(key)], " under /ontology/<domain>/")


def check_models(o: O.Ontology, lake, report: Report) -> None:
    table, rows = rows_of(o, lake, "model")
    for row in rows:
        if row.get(vla("model_class")) is not None:
            check_term(o, report, where(table, row), "model_class", row[vla("model_class")])


def check_datasets(o: O.Ontology, lake, report: Report) -> None:
    table, rows = rows_of(o, lake, "dataset")
    for row in rows:
        path, collection = where(table, row), row.get(vla("collection"))
        if not isinstance(collection, list) or not collection:
            report.error("project.dataset", path, "a Dataset needs collection: a list of collection-method terms")
            collection = []
        for value in collection:
            rel = term_rel(o, value)
            if rel is None:
                report.error("project.dataset", path, f"collection '{value}' is not a Term page")
            elif not in_family(o, rel, DATASETS):
                report.error("project.dataset", path,
                             f"collection '{value}' is not a term of the {DATASETS} ontology or one that extends it")
        for key in ("embodiments", "tasks", "modalities"):
            values = row.get(vla(key))
            for value in values if isinstance(values, list) else []:
                if term_rel(o, value) is None:
                    report.error("project.dataset", path, f"{key} entry '{value}' is not a Term page")


def check_trained_on(o: O.Ontology, lake, report: Report) -> None:
    models = {r.get("iri") for r in rows_of(o, lake, "model")[1]}
    datasets = {r.get("iri") for r in rows_of(o, lake, "dataset")[1]}
    table, rows = rows_of(o, lake, "trained-on")
    for row in rows:
        path = where(table, row)
        model, dataset, role = row.get(vla("model")), row.get(vla("dataset")), row.get(vla("role"))
        given = {"model": model, "dataset": dataset, "role": role, "evidence": media_refs(row.get(core("evidence")))}
        if missing := [k for k in TRAINED_ON if given[k] in (None, "", [])]:
            report.error("project.trained-on", path,
                         f"each trained_on row has model, dataset, role and evidence; this one has no {', '.join(missing)}")
        for key, value, known, table_name in (("model", model, models, "models"), ("dataset", dataset, datasets, "datasets")):
            if value is None:
                continue
            if not isinstance(value, str):  # a hand-retyped column; a list or number cannot be looked up
                report.error("project.trained-on", path, f"{key} {value!r} is not an IRI")
            elif value not in known:
                report.error("project.trained-on", path, f"{key} '{value}' is not a row of {table_name}")
        if role is not None:
            rel = term_rel(o, role)
            if rel is None or not in_family(o, rel, DATASETS):
                report.error("project.trained-on", path,
                             f"role '{role}' is not a term of the {DATASETS} ontology or one that extends it")


@dataclass
class Row:
    """A row of a bound VLA table, with the names of its table's columns."""

    table: str
    columns: list[str]
    values: dict


def vla_rows(o: O.Ontology, lake) -> dict[str, Row]:
    """Every row of the tables the VLA classes bind, by its IRI."""
    out = {}
    for k in sorted(o.classes.values(), key=lambda c: c.rel):
        table, rows = read_rows(lake, k) if k.iri.startswith(VLA) else ("", [])
        if not table:
            continue
        cur = lake.con.execute('SELECT * FROM "' + table.replace('"', '""') + '" LIMIT 0')
        columns = [d[0] for d in cur.description]
        out.update({row["iri"]: Row(table, columns, row) for row in rows if isinstance(row.get("iri"), str)})
    return out


def evidence_fault(rows: dict[str, Row], what: str, value) -> str | None:
    """Why value is not <row IRI>#evidence/<index> naming an entry of that row's evidence; None when it is."""
    m = EVIDENCE_REF.fullmatch(value) if isinstance(value, str) else None
    if m is None:
        return f"{what} {value!r} is not of the form {EVIDENCE_FORM}"
    row = rows.get(m["iri"])
    if row is None:
        return f"{what} '{value}' names no row of a VLA table"
    n = len(media_refs(row.values.get(core("evidence"))))
    if int(m["index"]) >= n:
        return f"{what} '{value}' names evidence entry {m['index']}, but that row has {n}"
    return None


def check_contested(o: O.Ontology, lake, report: Report) -> None:
    """project.contested: the claim and each statement that disputes it name an evidence entry of a row."""
    table, rows = rows_of(o, lake, "contested")
    known = vla_rows(o, lake) if rows else {}
    for row in rows:
        path, claim, disputed_by = where(table, row), row.get(vla("claim")), row.get(vla("disputed_by"))
        if claim in (None, ""):
            report.error("project.contested", path, f"a contested row needs a claim: {EVIDENCE_FORM}")
        elif message := evidence_fault(known, "claim", claim):
            report.error("project.contested", path, message)
        if not isinstance(disputed_by, list) or not disputed_by:
            report.error("project.contested", path, f"disputed_by must be a non-empty list of {EVIDENCE_FORM}")
            continue
        for value in disputed_by:
            message = evidence_fault(known, "disputed_by entry", value)
            if message is None and value == claim:
                message = f"disputed_by entry '{value}' is the claim itself"
            if message:
                report.error("project.contested", path, message)


def check_computations(o: O.Ontology, lake, report: Report) -> None:
    """project.computation: each input names a row of a VLA table and a column of that row's table."""
    table, rows = rows_of(o, lake, "computation")
    known = vla_rows(o, lake) if rows else {}
    for row in rows:
        path, inputs = where(table, row), row.get(vla("inputs"))
        if not isinstance(inputs, list) or not inputs:
            report.error("project.computation", path, f"a computation needs inputs: a non-empty list of {INPUT_FORM}")
            continue
        for value in inputs:
            iri, _, column = value.rpartition("#") if isinstance(value, str) else ("", "", "")
            if not iri or not column:
                report.error("project.computation", path, f"input {value!r} is not of the form {INPUT_FORM}")
            elif (found := known.get(iri)) is None:
                report.error("project.computation", path, f"input '{value}' names no row of a VLA table")
            elif column not in found.columns:
                report.error("project.computation", path,
                             f"input '{value}' names column '{column}', which is not a column of table {found.table}")


def check_entities(o: O.Ontology, lake, report: Report) -> None:
    """project.entity: no two rows of papers, models or datasets share a normalized title or alias."""
    owners: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for slug in ("paper", "model", "dataset"):
        table, rows = rows_of(o, lake, slug)
        for row in rows:
            aliases = row.get(core("aliases"))
            for name in [row.get(core("title"))] + (aliases if isinstance(aliases, list) else []):
                if isinstance(name, str) and V.normalize_name(name):
                    owners[V.normalize_name(name)].append((where(table, row), name))
    for _, entries in sorted(owners.items()):
        paths = sorted({p for p, _ in entries})
        if len(paths) > 1:
            names = ", ".join(sorted({name for _, name in entries}))
            for path in paths:
                others = ", ".join(p for p in paths if p != path)
                report.error("project.entity", path, f"the name {names} also names {others}; one entity gets one row")


def check_iris(o: O.Ontology, lake, report: Report) -> None:
    """project.iri: every row under the lake's iri_base, and every type a team adds under its team IRI."""
    cfg = getattr(lake, "config", None)
    if cfg is None:
        return  # a lake opened without its config names no team
    for k in sorted(o.classes.values(), key=lambda c: c.rel):
        table, rows = read_rows(lake, k)
        for row in rows:
            iri = row.get("iri")
            if not (isinstance(iri, str) and iri.startswith(cfg.iri_base)):
                report.error("project.iri", where(table, row),
                             f"row iri '{iri}' does not start with the lake's iri_base '{cfg.iri_base}'")
    team_base = f"{VLA}{cfg.team}/"
    for t in sorted([*o.classes.values(), *o.interfaces.values(), *o.props.values()], key=lambda t: t.rel):
        if t.iri not in seeded_types() and not t.iri.startswith(team_base):
            report.error("project.iri", t.rel,
                         f"type iri '{t.iri}' is not a seeded type, so it must start with '{team_base}', the IRI of team {cfg.team}")


def check_rows(o: O.Ontology, lake, report: Report) -> None:
    for check in (check_results, check_models, check_datasets, check_trained_on, check_contested, check_computations,
                  check_entities, check_iris):
        check(o, lake, report)
