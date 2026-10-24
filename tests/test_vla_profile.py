"""The VLA profile: the rules for Result, Dataset and model pages, and the three seed specs."""

import yaml
from conftest import GOOD_SOURCE, concept, errors, ontology, term

from kdb_tools import profile as P
from kdb_tools.validate import validate


def test_the_profile_is_installed_as_vla():
    assert [p.name for p in P.installed("vla")] == ["vla"]


def add_dataset_terms(bundle):
    ontology(bundle, "datasets")
    ontology(bundle, "vla-datasets", extends=["datasets"])
    ontology(bundle, "robotics")
    for label, domain, kind, broader in [
            ("Human-collected", "datasets", "collection", None),
            ("Pretraining", "datasets", "roles", None),
            ("Fine-tuning", "datasets", "roles", None),
            ("Teleoperation", "vla-datasets", "collection", "/ontology/datasets/collection/human-collected.md"),
            ("WidowX 250", "robotics", "embodiments", None),
            ("Pick and place", "robotics", "tasks", None),
            ("Vision-language-action model", "robotics", "models", None)]:
        rel, fm = term(label, domain=domain, kind=kind, **({"broader": [broader]} if broader else {}))
        bundle.add(rel, fm)


def add_terms(bundle):
    for label, kind in [("Pick and place", "tasks"), ("LIBERO", "benchmarks"), ("LIBERO-Long", "benchmarks"),
                        ("Franka Panda", "embodiments")]:
        rel, fm = term(label, kind=kind)
        bundle.add(rel, fm)


CONDITIONS = {
    "task": "/ontology/robotics/tasks/pick-and-place.md",
    "benchmark": "/ontology/robotics/benchmarks/libero.md",
    "suite": "/ontology/robotics/benchmarks/libero-long.md",
    "embodiment": "/ontology/robotics/embodiments/franka-panda.md",
    "trials": 500,
}


def test_a_result_states_its_conditions_as_ontology_terms(bundle):
    add_terms(bundle)
    bundle.add("results/openvla-libero.md", concept(type="Result", title="OpenVLA on LIBERO", conditions=CONDITIONS))
    assert errors(validate(bundle.root)) == []
    partial = {k: v for k, v in CONDITIONS.items() if k != "trials"}
    bundle.add("results/openvla-libero.md", concept(type="Result", title="OpenVLA on LIBERO", conditions=partial))
    found = [f for f in validate(bundle.root).findings if f.rule == "project.result"]
    assert found and "trials" in found[0].message


def test_a_condition_given_as_a_word_instead_of_a_term_fails(bundle):
    add_terms(bundle)
    bundle.add("results/openvla-libero.md", concept(type="Result", title="OpenVLA on LIBERO",
                                                    conditions=dict(CONDITIONS, task="pick and place")))
    found = [f for f in validate(bundle.root).findings if f.rule == "project.condition"]
    assert found and "task" in found[0].message


def test_a_condition_must_point_at_a_term_page(bundle):
    add_terms(bundle)
    bundle.add("models/openvla.md", concept())
    for value in ["/ontology/robotics/tasks/missing.md", "/models/openvla.md"]:
        bundle.add("results/openvla-libero.md", concept(type="Result", title="OpenVLA on LIBERO",
                                                        conditions=dict(CONDITIONS, task=value)))
        assert "project.condition" in errors(validate(bundle.root)), value


T = "/ontology"
DATASET = {"collection": [f"{T}/vla-datasets/collection/teleoperation.md"],
           "embodiments": [f"{T}/robotics/embodiments/widowx-250.md"],
           "tasks": [f"{T}/robotics/tasks/pick-and-place.md"]}


def trained_on(**over):
    entry = {"dataset": "/datasets/bridge.md", "role": f"{T}/datasets/roles/pretraining.md", "source": GOOD_SOURCE["id"]}
    entry.update(over)
    return [entry]


def test_a_dataset_page_names_its_collection_with_dataset_terms(bundle):
    add_dataset_terms(bundle)
    bundle.add("datasets/bridge.md", concept(type="Dataset", title="BridgeData V2", **DATASET))
    assert errors(validate(bundle.root)) == []
    bundle.add("datasets/bridge.md", concept(type="Dataset", title="BridgeData V2", **dict(DATASET, collection=["teleoperated"])))
    assert "project.dataset" in errors(validate(bundle.root))
    bundle.add("datasets/bridge.md", concept(type="Dataset", title="BridgeData V2",
                                             **dict(DATASET, collection=[f"{T}/robotics/tasks/pick-and-place.md"])))
    found = [f for f in validate(bundle.root).findings if f.rule == "project.dataset"]
    assert found and "datasets ontology" in found[0].message
    no_collection = {k: v for k, v in DATASET.items() if k != "collection"}
    bundle.add("datasets/bridge.md", concept(type="Dataset", title="BridgeData V2", **no_collection))
    assert "project.dataset" in errors(validate(bundle.root))


def test_a_model_trained_on_a_dataset_names_the_page_the_role_and_a_source(bundle):
    add_dataset_terms(bundle)
    bundle.add("datasets/bridge.md", concept(type="Dataset", title="BridgeData V2", **DATASET))
    bundle.add("models/openvla.md", concept(trained_on=trained_on(),
                                            model_class=f"{T}/robotics/models/vision-language-action-model.md"))
    assert errors(validate(bundle.root)) == []
    for bad in [trained_on(dataset="/datasets/missing.md"), trained_on(dataset="/models/openvla.md"),
                trained_on(role="pretraining"), trained_on(role=f"{T}/robotics/tasks/pick-and-place.md"),
                trained_on(source="not-a-source-here"), [{"dataset": "/datasets/bridge.md"}]]:
        bundle.add("models/openvla.md", concept(trained_on=bad))
        assert "project.trained-on" in errors(validate(bundle.root)), bad


def test_a_model_class_must_be_a_term(bundle):
    add_dataset_terms(bundle)
    bundle.add("models/openvla.md", concept(model_class="VLA"))
    assert "project.condition" in errors(validate(bundle.root))


def test_every_shipped_seed_is_well_formed():
    from importlib.resources import files
    specs = {f.name: yaml.safe_load(f.read_text()) for f in files("physical_ai_kdb.seeds").iterdir() if f.name.endswith(".yaml")}
    assert {"robotics.yaml", "datasets.yaml", "vla-datasets.yaml"} <= set(specs)
    domains = {s["domain"] for s in specs.values()}
    for s in specs.values():
        assert set(s.get("extends", [])) <= domains
        local = {t["slug"] for t in s["terms"]}
        for t in s["terms"]:
            for b in t.get("broader", []):
                assert ("/" in b and b.split("/")[0] in s.get("extends", [])) or b in local, (t["slug"], b)
            assert t["scope"] and all(q["quote"]["paper"] in s["papers"] for q in t["scope"]), t["slug"]
    assert specs["vla-datasets.yaml"]["extends"] == ["datasets"]
