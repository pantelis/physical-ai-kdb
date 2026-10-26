"""The Physical AI kDB profile for kdb-tools: VLA row rules, the VLA classes and the seed ontologies.

The kDB holds types: the Term ontologies (robotics, datasets, vla-datasets) and the VLA classes of
seeds/vla.yaml. Papers, models, datasets, results and the rest are rows of the tables those
classes bind. okf-seed writes the class pages; bind_tables then binds each class to its table.
"""

from importlib.resources import files

import yaml
from kdb_tools.actions.types import BindTable
from kdb_tools.profile import Profile

from .rules import check_rows

SEEDS = files(__name__) / "seeds"
PROFILE = Profile("vla", check_rows=check_rows, seeds=SEEDS)


def bindings() -> dict[str, dict]:
    """Each VLA class IRI mapped to the binding seeds/vla.yaml gives it, with full property IRIs."""
    spec = yaml.safe_load((SEEDS / "vla.yaml").read_text())
    base = spec["base_iri"]
    out = {}
    for entry in spec["classes"]:
        binding = dict(entry["binding"])
        binding["columns"] = {col: ref if "://" in ref else f"{base}properties/{ref}"
                              for col, ref in binding["columns"].items()}
        out[f"{base}classes/{entry['slug']}"] = binding
    return out


def bind_tables(ctx) -> list[str | None]:
    """Run BindTable for each VLA class, after okf-seed has written the core and VLA pages.

    The seeder does not write bindings: a binding creates a lake table, so only the BindTable action
    writes one. Each call is one logged action."""
    return [BindTable().submit(ctx, {"class_iri": iri, "binding": binding}) for iri, binding in bindings().items()]
