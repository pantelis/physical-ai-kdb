"""The VLA profile: the row rules for results, datasets, training links and models, and the seed specs.

Each test seeds the core and VLA classes into a bundle with a lake, binds their tables, writes rows
and runs okf-validate with the lake. Rows that an action would refuse are inserted with SQL, as a
row written outside an action would be: the rules report them and never raise.
"""

import dataclasses
import json

import pytest
import yaml
from conftest import domain, errors, klass, term

from kdb_tools import profile as P
from kdb_tools.actions import Context
from kdb_tools.actions.adopt import AdoptBundle
from kdb_tools.actions.objects import RegisterMedia, UpsertObjects
from kdb_tools.lake import Lake, LakeConfig, LocalStore
from kdb_tools.media import sha256_of
from kdb_tools.report import Report
from kdb_tools.seed import CORE_SEEDS, seed_action
from kdb_tools.validate import validate

from physical_ai_kdb import PROFILE, SEEDS, bind_tables

VLA = "https://kdb.aegean.ai/vla/"
DATA = "https://data.aegean.ai/vla/team-1/"
BASES = {"robotics": "https://kdb.aegean.ai/robotics/", "datasets": "https://kdb.aegean.ai/datasets/",
         "vla-datasets": "https://kdb.aegean.ai/vla-datasets/"}
SLUGS = ["paper", "model", "dataset", "trained-on", "result", "contested", "computation", "analysis"]
TABLES = ["papers", "models", "datasets", "trained_on", "results", "contested", "computations", "analyses"]


def cls(slug):
    return f"{VLA}classes/{slug}"


def iri(domain_name, kind, label):
    return f"{BASES[domain_name]}{kind}/{label.lower().replace(' ', '-')}"


def test_the_profile_is_installed_as_vla():
    assert [p.name for p in P.installed("vla")] == ["vla"]


TERMS = [  # (label, domain, kind, broader)
    ("Human-collected", "datasets", "collection", None),
    ("Pretraining", "datasets", "roles", None),
    ("Fine-tuning", "datasets", "roles", None),
    ("Teleoperation", "vla-datasets", "collection", "/ontology/datasets/collection/human-collected.md"),
    ("WidowX 250", "robotics", "embodiments", None),
    ("Pick and place", "robotics", "tasks", None),
    ("LIBERO", "robotics", "benchmarks", None),
    ("LIBERO-Long", "robotics", "benchmarks", None),
    ("Franka Panda", "robotics", "embodiments", None),
    ("Vision-language-action model", "robotics", "models", None),
]


def add_terms(bundle):
    domain(bundle, "datasets", BASES["datasets"])
    domain(bundle, "vla-datasets", BASES["vla-datasets"], extends=["datasets"])
    domain(bundle, "robotics", BASES["robotics"])
    for label, dom, kind, broader in TERMS:
        extra = {"broader": [broader]} if broader else {}
        bundle.add(*term(label, domain=dom, kind=kind, iri=iri(dom, kind, label), **extra))


def spec(name):
    folder = CORE_SEEDS if name == "core.yaml" else SEEDS
    return yaml.safe_load((folder / name).read_text())


@pytest.fixture
def ctx(bundle, tmp_path):
    """A bundle with the term ontologies, the core and VLA classes seeded, and every VLA table bound."""
    add_terms(bundle)
    cfg = LakeConfig(catalog=tmp_path / "meta.ducklake", data_path=str(tmp_path / "data") + "/", team="team-1",
                     iri_base=DATA)
    lake = Lake.open(cfg)
    lake.ensure_system_tables()
    c = Context(root=bundle.root, lake=lake, store=LocalStore(tmp_path / "data"), actor="a1", model=None,
                team="team-1", iri_base=DATA)
    AdoptBundle().submit(c, {})
    report = Report("test", extra={"written": [], "terms": 0, "types": 0})
    for name in ("core.yaml", "vla.yaml"):
        seed_action(c, name, spec(name), report)
    assert report.findings == []
    bind_tables(c)
    yield c
    lake.close()


def found(ctx, rule):
    return [f for f in validate(ctx.root, [PROFILE], lake=ctx.lake).findings if f.rule == rule]


def upsert(ctx, slug, *rows):
    UpsertObjects().submit(ctx, {"class_iri": cls(slug), "rows": list(rows)})


def insert(ctx, table, row):
    """A row written with SQL, outside any action: what a broken writer or a hand edit leaves."""
    cols = list(row)
    values = [json.dumps(v) if c == "evidence" and v is not None else v for c, v in row.items()]
    ctx.lake.con.execute(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})", values)


def evidence(ctx):
    """A MediaRef into the bundle's paper, registered in the media table."""
    RegisterMedia().submit(ctx, {"path": "papers/kim2024.pdf", "origin": "https://arxiv.org/abs/2406.09246"})
    sha = sha256_of((ctx.root / "papers/kim2024.pdf").read_bytes())
    return [{"sha256": sha, "page": 1, "bbox": [72, 700, 400, 714], "quote": "OpenVLA is trained on 970k robot episodes."}]


CONDITIONS = {
    "task": iri("robotics", "tasks", "Pick and place"),
    "benchmark": iri("robotics", "benchmarks", "LIBERO"),
    "suite": iri("robotics", "benchmarks", "LIBERO-Long"),
    "embodiment": iri("robotics", "embodiments", "Franka Panda"),
    "trials": 500,
}
RESULT = DATA + "results/openvla-libero"


def result(**over):
    return {"iri": RESULT, "title": "OpenVLA on LIBERO", "value": 76.5, "metric": "success rate", **CONDITIONS, **over}


# --- results ---

def test_a_result_states_its_conditions_as_ontology_terms(ctx):
    upsert(ctx, "result", result())
    assert found(ctx, "project.result") == [] and found(ctx, "project.condition") == []
    upsert(ctx, "result", result(trials=None))
    hits = found(ctx, "project.result")
    assert hits and "trials" in hits[0].message and hits[0].path == f"results/{RESULT}"


def test_a_result_without_a_trial_count_says_the_paper_gives_none(ctx):
    upsert(ctx, "result", result(trials=None, trials_reported=False))
    assert found(ctx, "project.result") == []
    upsert(ctx, "result", result(trials=None, trials_reported=True))
    assert "trials" in found(ctx, "project.result")[0].message


def test_a_result_missing_a_condition_names_it(ctx):
    upsert(ctx, "result", result(suite=None, embodiment=None))
    assert [f.message for f in found(ctx, "project.result")] == ["a Result needs conditions with suite, embodiment"]


def test_a_condition_given_as_a_word_instead_of_a_term_fails(ctx):
    upsert(ctx, "result", result(task="pick and place"))
    hits = found(ctx, "project.condition")
    assert hits and "task" in hits[0].message


def test_a_condition_must_name_a_term(ctx):
    model = DATA + "models/openvla"
    upsert(ctx, "model", {"iri": model, "title": "OpenVLA"})
    for value in [BASES["robotics"] + "tasks/missing", model, cls("result")]:
        insert(ctx, "results", {"iri": DATA + "results/r-" + value.rsplit("/", 1)[-1], "type": cls("result"),
                                "team": "team-1", "title": "r", **dict(CONDITIONS, task=value)})
    paths = sorted(f.path for f in found(ctx, "project.condition"))
    assert paths == sorted(f"results/{DATA}results/r-{v}" for v in ("missing", "openvla", "result"))


def test_a_condition_must_be_a_robotics_term(ctx):
    upsert(ctx, "result", result(task=iri("datasets", "roles", "Pretraining")))
    hits = found(ctx, "project.condition")
    assert hits and "robotics ontology" in hits[0].message


def test_a_model_class_must_be_a_term(ctx):
    upsert(ctx, "model", {"iri": DATA + "models/openvla", "title": "OpenVLA", "model_class": "VLA"})
    assert "project.condition" in errors(validate(ctx.root, [PROFILE], lake=ctx.lake))
    upsert(ctx, "model", {"iri": DATA + "models/openvla",
                          "model_class": iri("robotics", "models", "Vision-language-action model")})
    assert found(ctx, "project.condition") == []


# --- datasets and training links ---

BRIDGE = DATA + "datasets/bridge"
DATASET = {"iri": BRIDGE, "title": "BridgeData V2",
           "collection": [iri("vla-datasets", "collection", "Teleoperation")],
           "embodiments": [iri("robotics", "embodiments", "WidowX 250")],
           "tasks": [iri("robotics", "tasks", "Pick and place")]}


def test_a_dataset_names_its_collection_with_dataset_terms(ctx):
    upsert(ctx, "dataset", DATASET)
    assert found(ctx, "project.dataset") == []
    upsert(ctx, "dataset", dict(DATASET, collection=["teleoperated"]))
    assert [f.message for f in found(ctx, "project.dataset")] == ["collection 'teleoperated' is not a Term page"]
    upsert(ctx, "dataset", dict(DATASET, collection=[iri("robotics", "tasks", "Pick and place")]))
    hits = found(ctx, "project.dataset")
    assert hits and "datasets ontology" in hits[0].message
    upsert(ctx, "dataset", dict(DATASET, collection=None))
    assert [f.message for f in found(ctx, "project.dataset")] == ["a Dataset needs collection: a list of collection-method terms"]
    upsert(ctx, "dataset", dict(DATASET, collection=[]))
    assert found(ctx, "project.dataset")
    upsert(ctx, "dataset", dict(DATASET, tasks=["grasping"]))
    assert [f.message for f in found(ctx, "project.dataset")] == ["tasks entry 'grasping' is not a Term page"]


MODEL = DATA + "models/openvla"
LINK = DATA + "trained-on/openvla-bridge"


def test_a_model_trained_on_a_dataset_names_the_rows_the_role_and_evidence(ctx):
    upsert(ctx, "dataset", DATASET)
    upsert(ctx, "model", {"iri": MODEL, "title": "OpenVLA",
                          "model_class": iri("robotics", "models", "Vision-language-action model")})
    good = {"iri": LINK, "model": MODEL, "dataset": BRIDGE, "role": iri("datasets", "roles", "Pretraining"),
            "evidence": evidence(ctx)}
    upsert(ctx, "trained-on", good)
    assert found(ctx, "project.trained-on") == []
    for bad in [dict(good, dataset=DATA + "datasets/missing"), dict(good, dataset=MODEL),
                dict(good, model=DATA + "models/missing"), dict(good, role="pretraining"),
                dict(good, role=iri("robotics", "tasks", "Pick and place")), dict(good, evidence=[]),
                dict(good, evidence=None), dict(good, role=None)]:
        upsert(ctx, "trained-on", bad)
        assert found(ctx, "project.trained-on"), bad


# --- contested claims and computations ---

CONTESTED = DATA + "contested/openvla-libero"
COMPUTATION = DATA + "computations/mean"
EVIDENCE_FORM = "<row IRI>#evidence/<index>"


@pytest.fixture
def cited(ctx):
    """A model and a result, each with one evidence entry, for claims and inputs to point at."""
    ev = evidence(ctx)
    upsert(ctx, "model", {"iri": MODEL, "title": "OpenVLA", "evidence": ev})
    upsert(ctx, "result", result(model=MODEL, evidence=ev))
    return ev


def contested(ev, **over):
    return {"iri": CONTESTED, "claim": f"{RESULT}#evidence/0", "disputed_by": [f"{MODEL}#evidence/0"],
            "evidence": ev, **over}


def contested_messages(ctx):
    hits = found(ctx, "project.contested")
    assert all(f.path == f"contested/{CONTESTED}" for f in hits)
    return [f.message for f in hits]


def test_a_contested_claim_names_an_evidence_entry_of_a_row(ctx, cited):
    upsert(ctx, "contested", contested(cited))
    assert found(ctx, "project.contested") == []
    missing = f"{DATA}results/missing#evidence/0"
    for claim, message in [
        (None, f"a contested row needs a claim: {EVIDENCE_FORM}"),
        (RESULT, f"claim {RESULT!r} is not of the form {EVIDENCE_FORM}"),
        (f"{RESULT}#0", f"claim '{RESULT}#0' is not of the form {EVIDENCE_FORM}"),
        (f"{RESULT}#evidence/-1", f"claim '{RESULT}#evidence/-1' is not of the form {EVIDENCE_FORM}"),
        (missing, f"claim '{missing}' names no row of a VLA table"),
        (f"{RESULT}#evidence/1", f"claim '{RESULT}#evidence/1' names evidence entry 1, but that row has 1"),
    ]:
        upsert(ctx, "contested", contested(cited, claim=claim))
        assert contested_messages(ctx) == [message], claim


def test_disputed_by_lists_other_evidence_entries_of_rows(ctx, cited):
    whole = f"disputed_by must be a non-empty list of {EVIDENCE_FORM}"
    for disputed_by, message in [
        (None, whole),
        ([], whole),
        ([f"{MODEL}#title"], f"disputed_by entry '{MODEL}#title' is not of the form {EVIDENCE_FORM}"),
        ([f"{MODEL}#evidence/3"], f"disputed_by entry '{MODEL}#evidence/3' names evidence entry 3, but that row has 1"),
        ([f"{DATA}models/octo#evidence/0"], f"disputed_by entry '{DATA}models/octo#evidence/0' names no row of a VLA table"),
        ([f"{RESULT}#evidence/0"], f"disputed_by entry '{RESULT}#evidence/0' is the claim itself"),
    ]:
        upsert(ctx, "contested", contested(cited, disputed_by=disputed_by))
        assert contested_messages(ctx) == [message], disputed_by


def computation(**over):
    return {"iri": COMPUTATION, "title": "Mean success", "code": "value = 76.5", "inputs": [f"{RESULT}#value"],
            "value": 76.5, **over}


def test_a_computation_reads_columns_of_rows(ctx, cited):
    upsert(ctx, "computation", computation(inputs=[f"{RESULT}#value", f"{MODEL}#title"]))
    assert found(ctx, "project.computation") == []
    whole = "a computation needs inputs: a non-empty list of <row IRI>#<column>"
    missing = f"{DATA}results/missing#value"
    for inputs, message in [
        (None, whole),
        ([], whole),
        ([RESULT], f"input {RESULT!r} is not of the form <row IRI>#<column>"),
        ([f"{RESULT}#"], f"input '{RESULT}#' is not of the form <row IRI>#<column>"),
        ([missing], f"input '{missing}' names no row of a VLA table"),
        ([f"{RESULT}#score"], f"input '{RESULT}#score' names column 'score', which is not a column of table results"),
    ]:
        upsert(ctx, "computation", computation(inputs=inputs))
        hits = found(ctx, "project.computation")
        assert [(f.path, f.message) for f in hits] == [(f"computations/{COMPUTATION}", message)], inputs


def test_malformed_claims_and_inputs_are_findings_not_exceptions(ctx, cited):
    """Values a hand edit leaves: a null entry, a claim retyped as a number, a row whose evidence is not a list."""
    insert(ctx, "results", {"iri": DATA + "results/broken", "type": cls("result"), "team": "team-1",
                            "evidence": {"not": "a list"}})
    insert(ctx, "contested", {"iri": CONTESTED, "type": cls("contested"), "team": "team-1",
                              "claim": f"{DATA}results/broken#evidence/0", "disputed_by": [None]})
    insert(ctx, "computations", {"iri": COMPUTATION, "type": cls("computation"), "team": "team-1", "inputs": [None]})
    assert contested_messages(ctx) == [
        f"claim '{DATA}results/broken#evidence/0' names evidence entry 0, but that row has 0",
        f"disputed_by entry None is not of the form {EVIDENCE_FORM}"]
    assert [f.message for f in found(ctx, "project.computation")] == [
        "input None is not of the form <row IRI>#<column>"]
    ctx.lake.con.execute("DELETE FROM contested")
    ctx.lake.con.execute("ALTER TABLE contested DROP COLUMN claim")
    ctx.lake.con.execute("ALTER TABLE contested ADD COLUMN claim INTEGER")
    insert(ctx, "contested", {"iri": CONTESTED, "type": cls("contested"), "team": "team-1", "claim": 7,
                              "disputed_by": [f"{MODEL}#evidence/0"]})
    assert contested_messages(ctx) == [f"claim 7 is not of the form {EVIDENCE_FORM}"]


# --- names, IRIs and malformed rows ---

def test_two_rows_with_one_name_are_one_entity(ctx):
    upsert(ctx, "model", {"iri": MODEL, "title": "OpenVLA"})
    upsert(ctx, "dataset", dict(DATASET, aliases=["Open-VLA"]))
    hits = found(ctx, "project.entity")
    assert sorted(f.path for f in hits) == [f"datasets/{BRIDGE}", f"models/{MODEL}"]
    assert "one entity gets one row" in hits[0].message
    upsert(ctx, "dataset", dict(DATASET, aliases=[]))
    assert found(ctx, "project.entity") == []


def test_a_row_iri_is_under_the_lake_iri_base(ctx):
    other = "https://data.aegean.ai/vla/team-2/models/octo"
    insert(ctx, "models", {"iri": other, "type": cls("model"), "team": "team-2", "title": "Octo"})
    hits = found(ctx, "project.iri")
    assert [f.path for f in hits] == [f"models/{other}"] and DATA in hits[0].message


def test_a_type_the_team_adds_is_under_its_team_iri(ctx, bundle):
    domain(bundle, "team-1", f"{VLA}team-1/", extends=["vla"])
    klass(bundle, "team-1", "episode")
    domain(bundle, "rollouts", "https://kdb.aegean.ai/rollouts/")
    klass(bundle, "rollouts", "rollout")
    hits = found(ctx, "project.iri")
    assert [f.path for f in hits] == ["ontology/rollouts/classes/rollout.md"]
    assert f"{VLA}team-1/" in hits[0].message


def test_malformed_rows_are_findings_not_exceptions(ctx):
    insert(ctx, "results", {"iri": DATA + "results/bad", "type": cls("result"), "team": "team-1"})
    insert(ctx, "datasets", {"iri": DATA + "datasets/bad", "type": cls("dataset"), "team": "team-1",
                             "collection": [None], "embodiments": [None]})
    insert(ctx, "trained_on", {"iri": DATA + "trained-on/bad", "type": cls("trained-on"), "team": "team-1",
                               "evidence": {"not": "a list"}})
    insert(ctx, "models", {"iri": None, "type": cls("model"), "team": "team-1", "title": None})
    rules = {f.rule for f in validate(ctx.root, [PROFILE], lake=ctx.lake).findings}
    assert {"project.result", "project.dataset", "project.trained-on", "project.iri"} <= rules


def test_a_clean_seeded_bundle_with_one_row_per_class(ctx):
    ev = evidence(ctx)
    upsert(ctx, "paper", {"iri": DATA + "papers/2406.09246", "title": "OpenVLA: An Open-Source Vision-Language-Action Model",
                          "arxiv_id": "2406.09246", "version": "v3", "media": ev[0]["sha256"]})
    upsert(ctx, "model", {"iri": MODEL, "title": "OpenVLA", "aliases": ["openvla-7b"], "evidence": ev,
                          "model_class": iri("robotics", "models", "Vision-language-action model")})
    upsert(ctx, "dataset", dict(DATASET, evidence=ev))
    upsert(ctx, "trained-on", {"iri": LINK, "model": MODEL, "dataset": BRIDGE,
                               "role": iri("datasets", "roles", "Pretraining"), "evidence": ev})
    upsert(ctx, "result", result(model=MODEL, evidence=ev))
    upsert(ctx, "contested", {"iri": DATA + "contested/openvla-libero", "claim": f"{RESULT}#evidence/0",
                              "disputed_by": [f"{MODEL}#evidence/0"], "evidence": ev})
    upsert(ctx, "computation", {"iri": DATA + "computations/mean", "title": "Mean success", "code": "value = 76.5",
                                "inputs": [f"{RESULT}#value"], "value": 76.5})
    upsert(ctx, "analysis", {"iri": DATA + "analyses/best", "title": "Best model on LIBERO",
                             "question": "Which model does best on LIBERO-Long?", "answer": "OpenVLA",
                             "drew_on": [RESULT]})
    for table in TABLES:
        assert ctx.lake.con.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 1, table
    report = validate(ctx.root, [PROFILE], lake=ctx.lake)
    assert errors(report) == [], [(f.rule, f.path, f.message) for f in report.findings if f.level == "error"]


def test_without_a_lake_no_row_rule_runs(ctx):
    upsert(ctx, "result", result(task="pick and place", trials=None))
    assert not [f for f in validate(ctx.root, [PROFILE]).findings if f.rule.startswith("project.")]


# --- the seeds ---

def test_every_shipped_seed_is_well_formed():
    specs = {f.name: yaml.safe_load(f.read_text()) for f in SEEDS.iterdir() if f.name.endswith(".yaml")}
    assert {"robotics.yaml", "datasets.yaml", "vla-datasets.yaml", "vla.yaml"} <= set(specs)
    domains = {s["domain"] for s in specs.values()} | {"core"}
    for s in specs.values():
        assert set(s.get("extends", [])) <= domains
        assert s["base_iri"] == f"https://kdb.aegean.ai/{s['domain']}/"
        local = {t["slug"] for t in s.get("terms", [])}
        for t in s.get("terms", []):
            for b in t.get("broader", []):
                assert ("/" in b and b.split("/")[0] in s.get("extends", [])) or b in local, (t["slug"], b)
            assert t["scope"] and all(q["quote"]["paper"] in s["papers"] for q in t["scope"]), t["slug"]
    assert specs["vla-datasets.yaml"]["extends"] == ["datasets"]
    vla = specs["vla.yaml"]
    assert vla["extends"] == ["core"]
    assert sorted(c["binding"]["table"] for c in vla["classes"]) == sorted(TABLES)


def test_the_vla_classes_are_seeded_active_by_a_person_and_never_by_an_agent(ctx, bundle, tmp_path):
    from kdb_tools import onto as O
    from kdb_tools.actions import Failed
    from kdb_tools.bundle import load
    from kdb_tools.tools import NEEDS_A_PERSON, KdbTools

    classes = O.load_ontology(load(ctx.root)).classes
    assert {iri: classes[iri].status for iri in map(cls, SLUGS)} == dict.fromkeys(map(cls, SLUGS), "active")
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    (fresh / "index.md").write_text("# Fresh\n")
    cfg = LakeConfig(catalog=tmp_path / "fresh.ducklake", data_path=str(tmp_path / "fresh-data") + "/", team="team-1",
                     iri_base=DATA)
    lake = Lake.open(cfg)
    try:
        lake.ensure_system_tables()
        person = Context(root=fresh, lake=lake, store=LocalStore(tmp_path / "fresh-data"), actor="a1", model=None,
                         team="team-1", iri_base=DATA)
        AdoptBundle().submit(person, {})
        KdbTools(fresh, [], person).submit("SeedOntology", {"spec": spec("core.yaml")})
        agent = KdbTools(fresh, [], dataclasses.replace(person, actor="agent", model="m1"))
        with pytest.raises(Failed) as e:
            agent.submit("SeedOntology", {"spec": spec("vla.yaml")})
        assert e.value.messages == [NEEDS_A_PERSON]
        assert not (fresh / "ontology" / "vla").exists()
    finally:
        lake.close()


def test_a_model_or_dataset_that_is_not_text_is_a_finding(ctx):
    """A hand edit that retypes the columns as lists leaves values that cannot be looked up."""
    for col in ("model", "dataset"):
        ctx.lake.con.execute(f"ALTER TABLE trained_on DROP COLUMN {col}")
        ctx.lake.con.execute(f"ALTER TABLE trained_on ADD COLUMN {col} VARCHAR[]")
    insert(ctx, "trained_on", {"iri": LINK, "type": cls("trained-on"), "team": "team-1", "model": [MODEL],
                               "dataset": [BRIDGE]})
    messages = [f.message for f in found(ctx, "project.trained-on")]
    assert f"model {[MODEL]!r} is not an IRI" in messages
    assert f"dataset {[BRIDGE]!r} is not an IRI" in messages
