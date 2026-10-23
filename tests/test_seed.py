import hashlib

import yaml
from conftest import make_pdf

from kdb_tools.ground import ground
from kdb_tools.seed import seed
from kdb_tools.validate import validate

SENT = "We count pick-and-place as one skill since it is typically performed in one motion."
LIST = "The dataset includes skills such as pick-and-place, pushing, and more."


def spec(tmp_path, quote=SENT):
    s = {
        "domain": "robotics",
        "papers": {"bridge": "2308.12952"},
        "terms": [
            {"slug": "manipulation", "kind": "tasks", "pref_label": "Robot manipulation", "alt_labels": ["manipulation"],
             "scope": [{"text": "Robot manipulation covers skills such as pick-and-place and pushing.",
                        "quote": {"paper": "bridge", "page": 1, "text": LIST}}]},
            {"slug": "pick-and-place", "kind": "tasks", "pref_label": "Pick and place", "alt_labels": ["PnP"],
             "broader": ["manipulation"],
             "related_match": ["http://www.ease-crc.org/ont/SOMA.owl#PickingUp"],
             "scope": [{"text": "Pick-and-place is counted as one skill.",
                        "quote": {"paper": "bridge", "page": 2, "text": quote}}]},
        ],
    }
    path = tmp_path / "seed.yaml"
    path.write_text(yaml.safe_dump(s, sort_keys=False))
    return path


def paper(bundle):
    make_pdf(bundle.root / "papers" / "2308.12952.pdf", [[(72, 700, LIST)], [(72, 500, SENT)]])


def digest(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def test_seeding_writes_term_pages_that_pass_both_checks(bundle, tmp_path):
    paper(bundle)
    report = seed(bundle.root, spec(tmp_path))
    assert [f.rule for f in report.findings] == []
    page = (bundle.root / "ontology/robotics/tasks/pick-and-place.md").read_text()
    fm = yaml.safe_load(page.split("\n---\n", 1)[0][4:])
    assert fm["type"] == "Term" and fm["pref_label"] == "Pick and place"
    assert fm["broader"] == ["/ontology/robotics/tasks/manipulation.md"]
    assert fm["sources"][0]["page"] == 2 and fm["sources"][0]["resource"] == "/papers/2308.12952.pdf"
    assert errors(validate(bundle.root)) == []
    assert [f.rule for f in ground(bundle.root).findings] == []


def test_a_quote_that_is_not_in_the_paper_is_reported_and_its_term_is_not_written(bundle, tmp_path):
    paper(bundle)
    report = seed(bundle.root, spec(tmp_path, quote="A sentence the paper does not contain."))
    assert [f.rule for f in report.findings] == ["seed.quote"]
    assert "pick-and-place" in report.findings[0].message
    assert not (bundle.root / "ontology/robotics/tasks/pick-and-place.md").exists()


def test_a_missing_paper_is_reported(bundle, tmp_path):
    report = seed(bundle.root, spec(tmp_path))
    assert "seed.paper" in [f.rule for f in report.findings]
    assert "papers/2308.12952.pdf" in report.findings[0].message


def test_seeding_twice_changes_nothing(bundle, tmp_path):
    paper(bundle)
    s = spec(tmp_path)
    seed(bundle.root, s)
    before = digest(bundle.root)
    seed(bundle.root, s)
    assert digest(bundle.root) == before


def test_the_shipped_robotics_seed_is_well_formed():
    from importlib.resources import files
    s = yaml.safe_load(files("kdb_tools.seeds").joinpath("robotics.yaml").read_text())
    slugs = {t["slug"] for t in s["terms"]}
    for t in s["terms"]:
        assert set(t.get("broader", [])) <= slugs, t["slug"]
        assert t["scope"] and all(q["quote"]["paper"] in s["papers"] for q in t["scope"]), t["slug"]


def errors(report):
    return sorted({f.rule for f in report.findings if f.level == "error"})


def test_an_arxiv_id_that_yaml_reads_as_a_number_is_reported(bundle, tmp_path):
    path = spec(tmp_path)
    path.write_text(path.read_text().replace("'2308.12952'", "2306.03310"))
    report = seed(bundle.root, path)
    assert [f.rule for f in report.findings] == ["seed.spec"]
    assert "quote" in report.findings[0].message
