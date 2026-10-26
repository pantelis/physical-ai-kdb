"""The starter's plumbing works offline.

A scripted model stands in for the server, and the lake is a local DuckLake catalog with a data
folder, no RustFS. The long test walks the whole flow a student follows: lake init, the term seed,
ingest with a write_rows of the student's kind, the checks, export and restore.
"""

import dataclasses
import shutil
from pathlib import Path

import pytest
from fpdf import FPDF
from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from kdb_tools import config, guard
from kdb_tools import ground as G
from kdb_tools import media as M
from kdb_tools import validate as V
from kdb_tools.actions.objects import RegisterMedia, UpsertObjects
from kdb_tools.annotate import highlight
from kdb_tools.export import restore
from kdb_tools.lake import COMPOSE, Lake, load_config, store_for
from kdb_tools.report import Report
from kdb_tools.seed import seed_action
from kdb_tools.tools import KdbTools
from kdbagent import ask, cli, ingest
from kdbagent import lake as KL

STARTER = Path(__file__).resolve().parents[1]
QUOTE = "OpenVLA is trained on 970k robot episodes."
RESULT_QUOTE = "OpenVLA reaches 53.7 percent success on LIBERO-Long."
TERM_QUOTES = {  # (kind, slug, label): a sentence of the paper that defines the term
    ("tasks", "pick-and-place", "Pick and place"): "The robot picks up an object and places it in a basket.",
    ("benchmarks", "libero", "LIBERO"): "LIBERO is a benchmark for lifelong robot learning.",
    ("benchmarks", "libero-long", "LIBERO-Long"): "LIBERO-Long holds the long-horizon tasks of LIBERO.",
    ("embodiments", "franka-panda", "Franka Panda"): "All experiments use a Franka Panda arm.",
}
ROBOTICS = "https://kdb.aegean.ai/robotics/"
RESULT = "https://kdb.aegean.ai/vla/classes/result"
MODEL = "https://kdb.aegean.ai/vla/classes/model"
TEAM = "team-7"


def scripted(*outputs):
    """A model that returns each output in turn as its final answer, and records the retry prompts it saw."""
    seen = []

    def respond(messages, info: AgentInfo) -> ModelResponse:
        seen.extend(p.content for m in messages for p in m.parts if isinstance(p, RetryPromptPart))
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, outputs[min(respond.calls, len(outputs) - 1)])])

    respond.calls = 0

    def counted(messages, info):
        out = respond(messages, info)
        respond.calls += 1
        return out

    return FunctionModel(counted), seen


@pytest.fixture
def paper(tmp_path):
    """kdb/papers/2406.09246.pdf: one page with the evidence sentences and the term definitions."""
    pdf = FPDF(unit="pt", format="letter")
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    for n, line in enumerate([QUOTE, RESULT_QUOTE, *TERM_QUOTES.values()]):
        pdf.text(72, 100 + 20 * n, line)
    path = tmp_path / "project" / "kdb" / "papers" / "2406.09246.pdf"
    path.parent.mkdir(parents=True)
    pdf.output(str(path))
    return path


@pytest.fixture
def project(paper):
    """A student's project folder: kdb.toml copied from the example, and the kDB with one paper."""
    root = paper.parents[2]
    shutil.copyfile(STARTER / "kdb.toml.example", root / "kdb.toml")
    return root


def kdb(project, *args):
    return cli.main(["--config", str(project / "kdb.toml"), "--kdb", str(project / "kdb"), *args])


@pytest.fixture
def initialized(project, tmp_path, monkeypatch):
    """lake init, run from another folder, as a student might."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert kdb(project, "lake", "init", "--team", TEAM) == 0
    return project


@pytest.fixture
def ctx(initialized):
    c = KL.open_context(initialized / "kdb.toml", initialized / "kdb", model="scripted")
    yield c
    c.lake.close()


def action_count(project):
    c = KL.open_context(project / "kdb.toml", project / "kdb")
    try:
        return c.lake.con.execute("SELECT count(*) FROM kdb.action_log").fetchone()[0]
    finally:
        c.lake.close()


# --- the model server ---

def test_config_names_any_openai_compatible_server(tmp_path):
    (tmp_path / "kdb.toml").write_text('base_url = "http://localhost:8000/v1"\nmodel = "qwen3-32b"\ncontext = 32768\n')
    cfg = config.load(tmp_path / "kdb.toml")
    assert cfg.base_url == "http://localhost:8000/v1" and cfg.model == "qwen3-32b" and cfg.context == 32768
    assert config.model_from(cfg).model_name == "qwen3-32b"


def test_the_guard_refuses_a_prompt_the_server_would_cut():
    guard.check("short", context=32768)
    with pytest.raises(guard.PromptTooLong):
        guard.check("word " * 100_000, context=32768)


def test_openrouter_takes_its_key_from_the_environment(tmp_path, monkeypatch):
    (tmp_path / "kdb.toml").write_text('base_url = "https://openrouter.ai/api/v1"\nmodel = "qwen/qwen3-32b:free"\n'
                                       'api_key_env = "OPENROUTER_API_KEY"\n')
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    cfg = config.load(tmp_path / "kdb.toml")
    assert cfg.api_key == "sk-or-test" and config.model_from(cfg).model_name == "qwen/qwen3-32b:free"
    monkeypatch.delenv("OPENROUTER_API_KEY")
    with pytest.raises(config.ConfigError, match="OPENROUTER_API_KEY"):
        config.load(tmp_path / "kdb.toml")


def test_a_key_written_into_the_config_file_is_refused(tmp_path):
    (tmp_path / "kdb.toml").write_text('base_url = "https://openrouter.ai/api/v1"\nmodel = "x"\napi_key = "sk-or-secret"\n')
    with pytest.raises(config.ConfigError, match="api_key_env"):
        config.load(tmp_path / "kdb.toml")


def test_reasoning_effort_reaches_both_agents(tmp_path):
    (tmp_path / "kdb.toml").write_text('base_url = "http://localhost:11434/v1"\nmodel = "gemma4:31b-it-qat"\nreasoning_effort = "none"\n')
    cfg = config.load(tmp_path / "kdb.toml")
    assert config.settings_from(cfg) == {"openai_reasoning_effort": "none"}
    model = scripted({"facts": []})[0]
    assert ingest.make_agent(model, settings=config.settings_from(cfg)).model_settings == {"openai_reasoning_effort": "none"}
    assert ask.make_agent(model, settings=config.settings_from(cfg)).model_settings == {"openai_reasoning_effort": "none"}


def test_without_reasoning_effort_nothing_is_sent(tmp_path):
    (tmp_path / "kdb.toml").write_text('base_url = "http://localhost:11434/v1"\nmodel = "m"\n')
    assert config.settings_from(config.load(tmp_path / "kdb.toml")) == {}


# --- lake init ---

def test_lake_init_leaves_a_lake_you_can_use_at_once(initialized):
    assert config.load(initialized / "kdb.toml").model  # the model settings are still there
    cfg = load_config(initialized / "kdb.toml")
    assert cfg.team == TEAM and cfg.iri_base == f"https://data.aegean.ai/vla/{TEAM}/"
    assert not cfg.data_path.startswith("s3://") and cfg.catalog == initialized / "lake" / "catalog.ducklake"
    assert 'catalog = "lake/catalog.ducklake"' in (initialized / "kdb.toml").read_text()  # relative: the folder can move
    assert (initialized / "compose.yml").read_text() == COMPOSE.read_text()
    lake = Lake.open(cfg)
    try:
        tables = {t for (t,) in lake.con.execute("SELECT table_name FROM information_schema.tables "
                                                 "WHERE table_catalog = 'lake' AND table_schema = 'main'").fetchall()}
        report = V.validate(initialized / "kdb", lake=lake)
    finally:
        lake.close()
    assert {"papers", "models", "datasets", "trained_on", "results", "contested", "computations", "analyses"} <= tables
    assert report.findings == []


def test_lake_init_is_safe_to_run_again(initialized):
    log = (initialized / "kdb" / "log.md").read_text()
    before = action_count(initialized)
    assert kdb(initialized, "lake", "init", "--team", TEAM) == 0
    assert action_count(initialized) == before and (initialized / "kdb" / "log.md").read_text() == log


def test_lake_init_seeds_the_vla_classes_active_and_only_a_person_changes_them(initialized):
    """lake init runs as you, so it may create active classes and bind them. After that an agent may
    write rows but not change a class: adding a column to a table is for a person."""
    import physical_ai_kdb
    from kdb_tools.actions import Failed
    from kdb_tools.tools import NEEDS_A_PERSON

    person = KL.open_context(initialized / "kdb.toml", initialized / "kdb")
    try:
        mine = KdbTools(person.root, [], person)
        assert {c["iri"]: c["status"] for c in mine.list_classes()
                if c["iri"] in physical_ai_kdb.bindings()} == dict.fromkeys(physical_ai_kdb.bindings(), "active")
        binding = physical_ai_kdb.bindings()[MODEL]
        wider = dict(binding, columns=dict(binding["columns"], notes="https://kdb.aegean.ai/core/properties/description"))
        agent = KdbTools(person.root, [], dataclasses.replace(person, model="scripted"))
        with pytest.raises(Failed) as e:
            agent.submit("BindTable", {"class_iri": MODEL, "binding": wider})
        assert e.value.messages == [NEEDS_A_PERSON]
        assert mine.submit("BindTable", {"class_iri": MODEL, "binding": wider})["action_id"]
        assert "notes" in mine.get_class(MODEL)["binding"]["columns"]
    finally:
        person.lake.close()


def test_lake_init_refuses_another_team_for_the_same_lake(initialized, capsys):
    assert kdb(initialized, "lake", "init", "--team", "team-8") == 1
    assert TEAM in capsys.readouterr().err


def test_lake_init_refuses_a_team_that_cannot_be_part_of_an_iri(project, capsys):
    assert kdb(project, "lake", "init", "--team", "Team 7") == 1
    assert "team" in capsys.readouterr().err


def test_the_example_config_holds_no_secret_and_nothing_reads_cloud_keys():
    live = [ln.split("#", 1)[0].strip() for ln in (STARTER / "kdb.toml.example").read_text().splitlines()]
    assert not any(ln.startswith(("key =", "secret =", "api_key =")) for ln in live)
    code = "".join(p.read_text() for p in (STARTER / "kdbagent").glob("*.py"))
    assert not any(word in code for word in ("R2_", "AWS_", "CLOUDFLARE"))


def test_commands_need_a_lake_first(project, capsys):
    assert kdb(project, "export", str(project / "out")) == 1
    assert "kdb lake init" in capsys.readouterr().err


# --- ingest ---

def test_the_ingest_agent_sends_back_a_quote_that_is_not_on_the_page(paper):
    good = {"entity": "OpenVLA", "kind": "model", "sentence": "OpenVLA was trained on 970k episodes.", "quote": QUOTE, "page": 1}
    bad = dict(good, quote="OpenVLA is trained on one million episodes.")
    model, seen = scripted({"facts": [good, bad]}, {"facts": [good]})
    out = ingest.extract(ingest.make_agent(model), paper, [1], "PAPER text")
    assert [f.quote for f in out.facts] == [QUOTE]
    assert any("one million" in str(s) for s in seen)


def test_the_ingest_agent_can_look_quotes_up_itself(paper):
    agent = ingest.make_agent(scripted({"facts": []})[0], root=paper.parents[1])
    names = {name for ts in agent.toolsets for name in getattr(ts, "tools", {})}
    assert {"find_quote", "find_value", "find_cell", "check_pages"} <= names


FACT = {"entity": "OpenVLA", "kind": "model", "sentence": "OpenVLA reaches 53.7% on LIBERO-Long.", "quote": RESULT_QUOTE,
        "page": 1}


def test_ingest_registers_the_paper_and_leaves_the_rows_to_you(ctx, paper):
    agent = ingest.make_agent(scripted({"facts": [FACT]})[0])
    with pytest.raises(NotImplementedError, match="UpsertObjects") as e:
        ingest.ingest(ctx, paper, agent, context=32768)
    assert "dry_run" in str(e.value)
    row = M.lookup(ctx.lake, M.sha256_of(paper.read_bytes()))
    assert row["origin"] == "https://arxiv.org/abs/2406.09246" and ctx.store.exists(row["object_key"])


def seed_robotics_terms(ctx):
    """What okf-seed does with the papers of the library, here for four terms of this test's paper."""
    spec = {"domain": "robotics", "base_iri": ROBOTICS, "title": "Robotics", "description": "Test terms.",
            "papers": {"kim": "2406.09246"},
            "terms": [{"slug": slug, "kind": kind, "pref_label": label,
                       "scope": [{"text": f"{label} is a term.", "quote": {"paper": "kim", "page": 1, "text": quote}}]}
                      for (kind, slug, label), quote in TERM_QUOTES.items()]}
    report = Report("test", extra={"written": [], "terms": 0, "types": 0})
    seed_action(ctx, "robotics", spec, report)
    assert report.findings == []


def write_rows(ctx, paper, facts):
    """A student's write_rows, cut down to one Result row: highlight, register the copy, dry run, submit."""
    fact = facts[0]
    match = KdbTools(ctx.root).find_quote(paper.arxiv_id, fact.page, fact.quote)
    bbox = [min(b[0] for b in match.boxes), min(b[1] for b in match.boxes),
            max(b[2] for b in match.boxes), max(b[3] for b in match.boxes)]
    marked = ctx.root / "annotated" / paper.pdf.name
    assert highlight(paper.pdf, marked, [(fact.page, fact.quote, "result-1", bbox)]) == [True]
    RegisterMedia().submit(ctx, {"path": f"annotated/{paper.pdf.name}", "origin": "highlights by kdb ingest",
                                 "annotates": paper.sha256})
    iri = ctx.iri_base + "results/openvla-libero-long"
    row = {"iri": iri, "title": "OpenVLA on LIBERO-Long", "task": ROBOTICS + "tasks/pick-and-place",
           "benchmark": ROBOTICS + "benchmarks/libero", "suite": ROBOTICS + "benchmarks/libero-long",
           "embodiment": ROBOTICS + "embodiments/franka-panda", "trials_reported": False, "value": 53.7,
           "metric": "success rate",
           "evidence": [{"sha256": paper.sha256, "page": fact.page, "bbox": bbox, "quote": fact.quote}]}
    params = {"class_iri": RESULT, "rows": [row]}
    plan = UpsertObjects().dry_run(ctx, params)
    assert [r.op for r in plan.row_edits] == ["insert"]
    UpsertObjects().submit(ctx, params, plan)
    return [f"results/{iri}"]


def test_ingest_then_the_checks_then_export_and_restore(ctx, paper, initialized, monkeypatch, tmp_path):
    seed_robotics_terms(ctx)
    monkeypatch.setattr(ingest, "write_rows", write_rows)
    done = ingest.ingest(ctx, paper, ingest.make_agent(scripted({"facts": [FACT]})[0]), context=32768)
    assert [f.quote for f in done.facts] == [RESULT_QUOTE]
    assert done.rows == [f"results/{ctx.iri_base}results/openvla-libero-long"]
    assert done.checked.errors == [] and done.checked.warnings == []

    root = initialized / "kdb"
    assert V.validate(root, lake=ctx.lake).findings == []
    grounded = G.ground(root, lake=ctx.lake, store=ctx.store)
    assert grounded.findings == [] and grounded.extra["checked"] >= 5  # four term quotes and the row's evidence
    ctx.lake.close()
    assert V.main([str(root)]) == 0  # okf-validate and okf-ground find kdb.toml above the kDB
    assert G.main([str(root)]) == 0

    out = tmp_path / "drive"
    assert kdb(initialized, "export", str(out)) == 0
    [export] = list(out.iterdir())
    cfg = restore(export, tmp_path / "restored")
    lake = Lake.open(cfg)
    try:
        assert lake.con.execute("SELECT value FROM results").fetchall() == [(53.7,)]
        assert lake.con.execute("SELECT count(*) FROM kdb.media").fetchone()[0] == 2
        assert all(store_for(cfg).exists(k) for (k,) in lake.con.execute("SELECT object_key FROM kdb.media").fetchall())
    finally:
        lake.close()
    ctx.lake = Lake.open(load_config(initialized / "kdb.toml"))  # for the fixture to close


def test_kdb_ingest_says_write_rows_is_yours(initialized, paper, monkeypatch, capsys):
    monkeypatch.setattr(config, "model_from", lambda cfg: scripted({"facts": [FACT]})[0])
    assert kdb(initialized, "ingest", str(paper)) == 2
    err = capsys.readouterr().err
    assert "not written yet" in err and "UpsertObjects" in err


# --- ask ---

def test_the_ask_agent_reads_rows_not_pages():
    agent = ask.make_agent(scripted({"answerable": False})[0])
    names = {name for ts in agent.toolsets for name in getattr(ts, "tools", {})}
    assert {"query_objects", "get_object"} <= names and not {"list_pages", "read_page"} & names


def test_the_ask_agent_sends_back_evidence_that_is_not_on_the_row(ctx, paper):
    RegisterMedia().submit(ctx, {"path": "papers/2406.09246.pdf", "origin": "https://arxiv.org/abs/2406.09246"})
    sha = M.sha256_of(paper.read_bytes())
    iri = ctx.iri_base + "models/openvla"
    UpsertObjects().submit(ctx, {"class_iri": MODEL, "rows": [{"iri": iri, "title": "OpenVLA", "evidence": [
        {"sha256": sha, "page": 1, "bbox": [72, 680, 300, 694], "quote": QUOTE}]}]})
    claim = {"text": "OpenVLA was trained on 970k episodes.", "object": iri, "evidence": [0]}
    model, seen = scripted({"answerable": True, "claims": [dict(claim, evidence=[3])]},
                           {"answerable": True, "claims": [dict(claim, object=ctx.iri_base + "models/made-up")]},
                           {"answerable": True, "claims": [claim]})
    answer = ask.answer(ask.make_agent(model, retries=3), ctx, "What was OpenVLA trained on?")
    assert answer.claims[0].evidence == [0]
    assert any("evidence[3]" in str(s) for s in seen) and any("made-up" in str(s) for s in seen)


def test_commands_still_to_write_say_so(initialized, capsys):
    assert kdb(initialized, "history") == 2
    assert "not written yet" in capsys.readouterr().err


def test_a_missing_kdb_toml_says_to_copy_the_example(tmp_path, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert cli.main(["--config", str(empty / "kdb.toml"), "ask", "What is OpenVLA?"]) == 1
    assert "copy kdb.toml.example to kdb.toml" in capsys.readouterr().err


def test_a_model_run_that_fails_is_a_clear_message(initialized, monkeypatch, capsys):
    from pydantic_ai.exceptions import UnexpectedModelBehavior

    def fails(*args, **kwargs):
        raise UnexpectedModelBehavior("Exceeded maximum retries (1) for output validation")

    monkeypatch.setattr(ask, "answer", fails)
    assert kdb(initialized, "ask", "What is OpenVLA?") == 1
    assert capsys.readouterr().err == ("kdb ask: the model run failed: Exceeded maximum retries (1) for output "
                                       "validation\n")
