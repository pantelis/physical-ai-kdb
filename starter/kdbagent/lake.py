"""kdb lake init, and the Context that every other command acts in.

Your lake holds every paper, model, dataset and result as a row, and the kDB holds their types.
`kdb lake init --team <team>` makes a lake you can use at once: it adds a [lake] table to kdb.toml
(a local catalog and data folder, unless you point it at RustFS), writes compose.yml for RustFS,
creates the system tables, seeds the core and VLA ontologies through the SeedOntology action and
binds each VLA class to its table. Running it again changes nothing that is already in place.

The lake never needs a cloud credential. For RustFS, kdb.toml names the environment variables that
hold its key and secret (key_env, secret_env); compose.yml has local defaults for your own machine.
"""

from __future__ import annotations

import getpass
import json
import re
import tomllib
from pathlib import Path

import yaml
from kdb_tools import lake as L
from kdb_tools.actions import Context, Failed
from kdb_tools.actions.adopt import AdoptBundle
from kdb_tools.actions.types import SeedOntology, binding_dict, find_class, parse_binding, table_columns
from kdb_tools.report import Report
from kdb_tools.seed import CORE_SEEDS, seed_action

import physical_ai_kdb

TEAM = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
IRI_BASE = "https://data.aegean.ai/vla/{team}/"
LAKE_TABLE = """
[lake]
# Written by `kdb lake init`. Paths are relative to this file. See kdb.toml.example for RustFS.
catalog = "lake/catalog.ducklake"
data_path = "lake/data/"
team = "{team}"
iri_base = "{iri_base}"
"""


class LakeError(Exception):
    """Something the student has to fix; the message says what."""


def find_config(start: Path | None = None) -> Path:
    """The nearest kdb.toml in start (default: the current folder) or above it, else start/kdb.toml."""
    start = (start or Path.cwd()).absolute()
    for d in [start, *start.parents]:
        if (d / "kdb.toml").is_file():
            return d / "kdb.toml"
    return start / "kdb.toml"


def lake_config(config: Path) -> L.LakeConfig:
    try:
        cfg = L.load_config(config)
    except FileNotFoundError:
        raise LakeError(f"there is no {config}; copy kdb.toml.example to kdb.toml")
    except (ValueError, KeyError, tomllib.TOMLDecodeError) as e:  # ConfigError is a ValueError
        raise LakeError(f"cannot read the [lake] table of {config}: {e}")
    if cfg is None:
        raise LakeError(f"{config} has no [lake] table; run `kdb lake init --team <team>` first")
    return cfg


def open_context(config: Path, bundle: Path, model: str | None = None, actor: str | None = None) -> Context:
    """The Context for actions on the kDB and its lake. model is the agent's model id, or None for you."""
    cfg = lake_config(config)
    if not Path(cfg.catalog).exists():
        raise LakeError(f"the lake catalog {cfg.catalog} does not exist; run `kdb lake init --team {cfg.team}` first")
    lake = L.Lake.open(cfg)
    try:
        found = lake.con.execute("SELECT count(*) FROM information_schema.tables WHERE table_catalog = 'lake' "
                                 "AND table_schema = 'kdb' AND table_name = 'action_log'").fetchone()[0]
        if not found:
            raise LakeError(f"the lake at {cfg.catalog} has no action log; run `kdb lake init --team {cfg.team}`")
        return Context(root=Path(bundle), lake=lake, store=L.store_for(cfg), actor=actor or getpass.getuser(),
                       model=model, team=cfg.team, iri_base=cfg.iri_base)
    except BaseException:
        lake.close()
        raise


def init(config: Path, bundle: Path, team: str, actor: str | None = None) -> list[str]:
    """Make the lake ready and return a line for each thing done. Safe to run again."""
    if not TEAM.fullmatch(team):
        raise LakeError(f"the team {team!r} goes into every IRI, so use lowercase letters, digits and hyphens, "
                        "such as team-7")
    config, bundle = Path(config).absolute(), Path(bundle).absolute()
    if not config.is_file():
        raise LakeError(f"there is no {config}; copy kdb.toml.example to kdb.toml first")
    done = [*_write_lake_table(config, team), *_write_compose(config.parent)]
    cfg = lake_config(config)
    if cfg.team != team:
        raise LakeError(f"{config} already names team {cfg.team}; one lake belongs to one team")
    Path(cfg.catalog).parent.mkdir(parents=True, exist_ok=True)  # the catalog is a local file either way
    if cfg.data_path.startswith("s3://"):
        done += _ensure_bucket(cfg)
    else:
        Path(cfg.data_path).mkdir(parents=True, exist_ok=True)
    bundle.mkdir(parents=True, exist_ok=True)
    lake = L.Lake.open(cfg)
    try:
        lake.ensure_system_tables()
        ctx = Context(root=bundle, lake=lake, store=L.store_for(cfg), actor=actor or getpass.getuser(), model=None,
                      team=cfg.team, iri_base=cfg.iri_base)
        done += _adopt(ctx) + _seed(ctx) + _bind(ctx)
    finally:
        lake.close()
    return done


def _write_lake_table(config: Path, team: str) -> list[str]:
    text = config.read_text()
    if "lake" in tomllib.loads(text):
        return []
    config.write_text(text.rstrip("\n") + "\n" + LAKE_TABLE.format(team=team, iri_base=IRI_BASE.format(team=team)))
    return [f"added a local [lake] table for {team} to {config}"]


def _write_compose(folder: Path) -> list[str]:
    target = folder / "compose.yml"
    if target.exists():
        return []
    target.write_text(L.COMPOSE.read_text())
    return [f"wrote {target} (RustFS, for when you move the lake to S3 storage)"]


def _ensure_bucket(cfg: L.LakeConfig) -> list[str]:
    """RustFS starts with no buckets; DuckLake needs the one data_path names."""
    from botocore.exceptions import BotoCoreError, ClientError

    store = L.store_for(cfg)
    try:
        store.client.head_bucket(Bucket=store.bucket)
        return []
    except ClientError as e:
        if e.response["Error"]["Code"] not in ("404", "NoSuchBucket", "NotFound"):
            raise LakeError(f"cannot reach bucket {store.bucket} at {cfg.s3_endpoint}: {e}")
    except BotoCoreError as e:
        raise LakeError(f"cannot reach {cfg.s3_endpoint}; is RustFS running (docker compose up -d)? {e}")
    store.client.create_bucket(Bucket=store.bucket)
    return [f"created bucket {store.bucket} at {cfg.s3_endpoint}"]


def _adopt(ctx: Context) -> list[str]:
    """Bring pages written before the lake existed into the action log, once. A new kDB gets an index.md."""
    logged = ctx.lake.con.execute("SELECT page_edits FROM kdb.action_log").fetchall()
    if any(json.loads(e) if isinstance(e, str) else e for (e,) in logged):
        return []
    if not (ctx.root / "index.md").exists():
        (ctx.root / "index.md").write_text(f"# The kDB of {ctx.team}\n")
    AdoptBundle().submit(ctx, {})
    return ["logged the pages already in the kDB (AdoptBundle)"]


def _seed(ctx: Context) -> list[str]:
    done = []
    for name, path in (("core", CORE_SEEDS / "core.yaml"), ("vla", physical_ai_kdb.SEEDS / "vla.yaml")):
        spec = yaml.safe_load(path.read_text())
        if not SeedOntology().dry_run(ctx, {"spec": spec}).page_edits:
            continue  # already seeded; another run would only log an empty action
        report = Report("kdb lake init", extra={"written": [], "terms": 0, "types": 0})
        seed_action(ctx, name, spec, report)
        if report.errors:
            raise LakeError("\n".join(f"{f.rule} {f.path}: {f.message}" for f in report.findings if f.level == "error"))
        done.append(f"seeded the {name} ontology (SeedOntology)")
    return done


def _bind(ctx: Context) -> list[str]:
    def bound(iri: str, binding: dict) -> bool:
        _, _, k = find_class(ctx, iri)
        return binding_dict(k) == parse_binding(binding)[0] and table_columns(ctx, binding["table"]) is not None

    if all(bound(iri, b) for iri, b in physical_ai_kdb.bindings().items()):
        return []
    try:
        physical_ai_kdb.bind_tables(ctx)
    except Failed as e:
        raise LakeError("\n".join(e.messages))
    return ["bound each VLA class to its table (BindTable)"]
