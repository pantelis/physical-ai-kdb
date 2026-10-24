"""The Physical AI kDB profile for kdb-tools: VLA page rules and the seed ontology."""

from importlib.resources import files

from kdb_tools.profile import Profile

from .rules import check_page

PROFILE = Profile("vla", check_page=check_page, seeds=files(__name__) / "seeds")
