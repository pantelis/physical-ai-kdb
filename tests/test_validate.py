import json

from conftest import GOOD_BODY, GOOD_CELL, GOOD_SOURCE, concept

from paiw_tools.validate import main, validate


def rules(report):
    return sorted({(f.rule, f.level) for f in report.findings})


def errors(report):
    return sorted({f.rule for f in report.findings if f.level == "error"})


def test_a_well_formed_bundle_has_no_findings(bundle):
    bundle.add("models/openvla.md", concept())
    assert rules(validate(bundle.root)) == []


def test_a_page_without_frontmatter_breaks_okf_conformance(bundle):
    bundle.write("models/bad.md", "# Just a heading\n")
    assert "okf.frontmatter" in errors(validate(bundle.root))


def test_unparseable_yaml_breaks_okf_conformance(bundle):
    bundle.write("models/bad.md", "---\ntype: [unclosed\n---\n\nBody.\n")
    assert "okf.frontmatter" in errors(validate(bundle.root))


def test_a_page_without_type_breaks_okf_conformance(bundle):
    fm = concept()
    del fm["type"]
    bundle.add("models/openvla.md", fm)
    assert "okf.type" in errors(validate(bundle.root))


def test_index_files_carry_no_frontmatter_except_root_okf_version(bundle):
    bundle.add("models/openvla.md", concept())
    bundle.write("models/index.md", "---\ntitle: Models\n---\n\n# Models\n")
    assert "okf.index" in errors(validate(bundle.root))
    bundle.write("models/index.md", "# Models\n\n* [OpenVLA](openvla.md) - a model\n")
    root_index = (bundle.root / "index.md").read_text()
    bundle.write("index.md", "---\nokf_version: 0.2\n---\n\n" + root_index)
    assert "okf.index" not in errors(validate(bundle.root))


def test_log_date_headings_must_be_iso_dates(bundle):
    bundle.write("log.md", "# Update log\n\n## November 2\n* Built.\n")
    assert "okf.log" in errors(validate(bundle.root))


def test_the_root_needs_an_index_and_a_log(bundle):
    (bundle.root / "index.md").unlink()
    (bundle.root / "log.md").unlink()
    assert {"project.index", "project.log"} <= set(errors(validate(bundle.root)))


def test_every_concept_must_be_listed_in_an_index(bundle):
    bundle.add("models/openvla.md", concept())
    bundle.add("models/octo.md", concept(title="Octo"), index=False)
    findings = [f for f in validate(bundle.root).findings if f.rule == "project.index"]
    assert [f.path for f in findings] == ["models/octo.md"]


def test_a_concept_needs_a_generated_stamp(bundle):
    fm = concept()
    del fm["generated"]
    bundle.add("models/openvla.md", fm)
    assert "project.generated" in errors(validate(bundle.root))
    bundle.add("models/openvla.md", concept(generated={"by": "agent/x", "at": "yesterday"}))
    assert "project.generated" in errors(validate(bundle.root))


def test_a_table_cell_source_is_well_formed(bundle):
    body = "OpenVLA scores 76.5% on LIBERO.[^kim2024-t1-r2-c3]\n"
    bundle.add("models/openvla.md", concept(sources=[dict(GOOD_CELL)]), body)
    assert errors(validate(bundle.root)) == []


def test_a_source_must_be_a_sentence_or_a_table_cell(bundle):
    broken = dict(GOOD_SOURCE)
    del broken["quote"]
    bundle.add("models/openvla.md", concept(sources=[broken]))
    assert "project.source" in errors(validate(bundle.root))


def test_a_bbox_is_four_numbers_with_positive_size(bundle):
    for bbox in ([1, 2, 3], [10, 10, 5, 20], "72 700 400 714"):
        bundle.add("models/openvla.md", concept(sources=[dict(GOOD_SOURCE, bbox=bbox)]))
        assert "project.source" in errors(validate(bundle.root)), bbox


def test_source_ids_are_unique_on_a_page(bundle):
    bundle.add("models/openvla.md", concept(sources=[dict(GOOD_SOURCE), dict(GOOD_SOURCE)]))
    assert "project.source" in errors(validate(bundle.root))


def test_a_source_resource_must_exist_in_the_bundle(bundle):
    bundle.add("models/openvla.md", concept(sources=[dict(GOOD_SOURCE, resource="/papers/missing.pdf")]))
    assert "project.source" in errors(validate(bundle.root))


def test_a_relative_resource_names_where_it_was_looked_for_and_the_root_path(bundle):
    bundle.add("models/openvla.md", concept(sources=[dict(GOOD_SOURCE, resource="papers/kim2024.pdf")]))
    [msg] = [f.message for f in validate(bundle.root).findings if f.rule == "project.source"]
    assert "models/papers/kim2024.pdf" in msg
    assert "/papers/kim2024.pdf" in msg.replace("models/papers", "")


def test_a_log_without_date_headings_fails(bundle):
    bundle.write("log.md", "# Update log\n\n- 2026-11-02: Built the wiki.\n")
    assert "project.log" in errors(validate(bundle.root))


def test_every_citation_resolves_to_a_source_on_the_page(bundle):
    body = "OpenVLA is trained on robot episodes.[^nobody2024]\n\n[^nobody2024]: Nobody\n"
    bundle.add("models/openvla.md", concept(), body)
    report = validate(bundle.root)
    assert "project.citation" in errors(report)
    assert ("project.unused-source", "warning") in rules(report)


def test_a_cited_label_without_a_definition_is_a_warning(bundle):
    bundle.add("models/openvla.md", concept(), "OpenVLA is trained on robot episodes.[^kim2024-p3-s2]\n")
    assert rules(validate(bundle.root)) == [("project.footnote", "warning")]


def test_prose_sentences_without_a_citation_are_warnings(bundle):
    body = GOOD_BODY + "\nIt is the best model ever made. It also runs fast.[^kim2024-p3-s2]\n"
    bundle.add("models/openvla.md", concept(), body)
    found = [f for f in validate(bundle.root).findings if f.rule == "project.uncited"]
    assert len(found) == 1 and "best model" in found[0].message


def test_headings_lists_and_code_are_not_prose(bundle):
    body = "# OpenVLA\n\n```python\nx = 1\n```\n\n" + GOOD_BODY
    bundle.add("models/openvla.md", concept(), body)
    assert rules(validate(bundle.root)) == []


def test_aliases_are_a_list_of_strings(bundle):
    bundle.add("models/openvla.md", concept(aliases="openvla"))
    assert "project.aliases" in errors(validate(bundle.root))


def test_two_pages_for_one_entity_collide_after_normalization(bundle):
    bundle.add("models/openvla-oft.md", concept(title="OpenVLA-OFT"))
    bundle.add("models/oft.md", concept(title="OFT", aliases=["openvla oft"]))
    found = [f for f in validate(bundle.root).findings if f.rule == "project.entity"]
    assert found and found[0].level == "error"


def test_pi_is_written_as_pi_when_names_are_compared(bundle):
    bundle.add("models/pi0.md", concept(title="π0"))
    bundle.add("models/pi0-copy.md", concept(title="Pi0 copy", aliases=["pi0"]))
    assert "project.entity" in errors(validate(bundle.root))


def test_aliases_that_differ_after_normalization_do_not_collide(bundle):
    bundle.add("models/pi0.md", concept(title="π0", aliases=["pi-zero"]))
    bundle.add("models/pi05.md", concept(title="π0.5"))
    assert "project.entity" not in errors(validate(bundle.root))


def test_contested_by_maps_a_local_source_to_sources_in_the_bundle(bundle):
    newer = dict(GOOD_SOURCE, id="fei2025-t2-r3-c9", quote="A newer claim.")
    bundle.add("results/plus.md", concept(title="LIBERO-Plus result", sources=[newer]),
               "A newer claim.[^fei2025-t2-r3-c9]\n")
    bundle.add("models/openvla.md", concept(contested_by={"kim2024-p3-s2": ["fei2025-t2-r3-c9"]}))
    assert errors(validate(bundle.root)) == []
    bundle.add("models/openvla.md", concept(contested_by={"kim2024-p3-s2": ["ghost-id"]}))
    assert "project.contested" in errors(validate(bundle.root))
    bundle.add("models/openvla.md", concept(contested_by={"not-on-page": ["fei2025-t2-r3-c9"]}))
    assert "project.contested" in errors(validate(bundle.root))
    bundle.add("models/openvla.md", concept(contested_by=["fei2025-t2-r3-c9"]))
    assert "project.contested" in errors(validate(bundle.root))


def test_a_result_states_its_conditions(bundle):
    conditions = {"benchmark": "LIBERO", "suite": "LIBERO-Long", "trials": 500, "embodiment": "Franka"}
    bundle.add("results/openvla-libero.md", concept(type="Result", title="OpenVLA on LIBERO", conditions=conditions))
    assert errors(validate(bundle.root)) == []
    partial = {k: v for k, v in conditions.items() if k != "trials"}
    bundle.add("results/openvla-libero.md", concept(type="Result", title="OpenVLA on LIBERO", conditions=partial))
    found = [f for f in validate(bundle.root).findings if f.rule == "project.result"]
    assert found and "trials" in found[0].message


def test_an_attested_computation_runs_python(bundle):
    body = "# Computation\n\n```python\nprint(1)\n```\n\nThe mean gain.[^kim2024-p3-s2]\n"
    fm = concept(type="Attested Computation", title="Mean LIBERO gain", runtime="python")
    bundle.add("computations/gain.md", fm, body)
    assert errors(validate(bundle.root)) == []
    bundle.add("computations/gain.md", dict(fm, runtime="bigquery"), body)
    assert "project.computation" in errors(validate(bundle.root))
    bundle.add("computations/gain.md", fm, "No code here.[^kim2024-p3-s2]\n")
    assert "project.computation" in errors(validate(bundle.root))
    bundle.write("references/gain.py", "print(1)\n")
    bundle.add("computations/gain.md", dict(fm, computation="/references/gain.py"), "No fence.[^kim2024-p3-s2]\n")
    assert "project.computation" not in errors(validate(bundle.root))


def test_main_prints_json_and_exits_1_on_errors(bundle, capsys):
    bundle.add("models/openvla.md", concept(sources=[dict(GOOD_SOURCE, resource="/papers/missing.pdf")]))
    assert main([str(bundle.root), "--json"]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["tool"] == "okf-validate" and out["ok"] is False and out["errors"] >= 1
    assert {"rule", "level", "path", "message"} <= set(out["findings"][0])


def test_main_exits_0_when_clean_and_2_when_the_directory_is_missing(bundle, tmp_path, capsys):
    bundle.add("models/openvla.md", concept())
    assert main([str(bundle.root)]) == 0
    assert main([str(tmp_path / "nowhere")]) == 2
