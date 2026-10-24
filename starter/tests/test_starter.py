"""The starter's plumbing works offline: a scripted model stands in for the server."""

import json

import pytest
from fpdf import FPDF
from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from kdbagent import ask, cli, config, guard, ingest

QUOTE = "OpenVLA is trained on 970k robot episodes."


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
    pdf = FPDF(unit="pt", format="letter")
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    pdf.text(72, 100, QUOTE)
    path = tmp_path / "2406.09246.pdf"
    pdf.output(str(path))
    return path


def test_config_names_any_openai_compatible_server(tmp_path):
    (tmp_path / "kdb.toml").write_text('base_url = "http://localhost:8000/v1"\nmodel = "qwen3-32b"\ncontext = 32768\n')
    cfg = config.load(tmp_path / "kdb.toml")
    assert cfg.base_url == "http://localhost:8000/v1" and cfg.model == "qwen3-32b" and cfg.context == 32768
    assert config.model_from(cfg).model_name == "qwen3-32b"


def test_the_guard_refuses_a_prompt_the_server_would_cut():
    guard.check("short", context=32768)
    with pytest.raises(guard.PromptTooLong):
        guard.check("word " * 100_000, context=32768)


def test_the_ingest_agent_sends_back_a_quote_that_is_not_on_the_page(paper):
    good = {"entity": "OpenVLA", "kind": "model", "sentence": "OpenVLA was trained on 970k episodes.", "quote": QUOTE, "page": 1}
    bad = dict(good, quote="OpenVLA is trained on one million episodes.")
    model, seen = scripted({"facts": [good, bad]}, {"facts": [good]})
    out = ingest.extract(ingest.make_agent(model), paper, [1], "PAPER text")
    assert [f.quote for f in out.facts] == [QUOTE]
    assert any("one million" in str(s) for s in seen)


def test_the_ask_agent_sends_back_a_source_id_that_is_not_on_the_page(tmp_path):
    root = tmp_path / "kdb"
    (root / "models").mkdir(parents=True)
    (root / "models" / "openvla.md").write_text(
        "---\ntype: Model\ntitle: OpenVLA\nsources:\n- id: kim-p1-1\n  resource: /papers/2406.09246.pdf\n  page: 1\n"
        f"  quote: {json.dumps(QUOTE)}\n---\n\nOpenVLA is trained on 970k episodes.[^kim-p1-1]\n")
    claim = {"text": "OpenVLA was trained on 970k episodes.", "page": "models/openvla.md", "source_ids": ["kim-p1-1"]}
    model, seen = scripted({"answerable": True, "claims": [dict(claim, source_ids=["made-up"])]},
                           {"answerable": True, "claims": [claim]})
    answer = ask.answer(ask.make_agent(model), root, "What was OpenVLA trained on?")
    assert answer.claims[0].source_ids == ["kim-p1-1"]
    assert any("made-up" in str(s) for s in seen)


def test_commands_still_to_write_say_so(capsys):
    assert cli.main(["history"]) == 2
    assert "not written yet" in capsys.readouterr().err


def test_the_ingest_agent_can_look_quotes_up_itself(paper):
    agent = ingest.make_agent(scripted({"facts": []})[0], root=paper.parent)
    names = {name for ts in agent.toolsets for name in getattr(ts, "tools", {})}
    assert {"find_quote", "find_value", "check_pages"} <= names


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
