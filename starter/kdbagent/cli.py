"""The kdb command: lake init, ingest, ask, export and history.

kdb finds kdb.toml in the current folder or the nearest folder above it, and the kDB in the kdb
folder next to it, so you can run it from anywhere inside your project.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb
from kdb_tools import config, guard
from kdb_tools.actions import Failed
from kdb_tools.export import ExportError, export
from pydantic_ai.exceptions import AgentRunError

from . import ask, ingest
from . import lake as KL


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="kdb")
    p.add_argument("--config", type=Path, help="kdb.toml; default: the nearest one in or above this folder")
    p.add_argument("--kdb", type=Path, help="the kDB bundle; default: the kdb folder next to kdb.toml")
    sub = p.add_subparsers(dest="cmd", required=True)
    lake = sub.add_parser("lake", help="set up your lake").add_subparsers(dest="lake_cmd", required=True)
    init = lake.add_parser("init", help="make the lake, seed the ontologies and bind the tables")
    init.add_argument("--team", required=True, help="your team or student id, such as team-7; it goes into every IRI")
    i = sub.add_parser("ingest", help="add one paper to the lake")
    i.add_argument("pdf", type=Path)
    i.add_argument("--origin", help="where the PDF came from; default: its arXiv page")
    a = sub.add_parser("ask", help="answer a question from the lake")
    a.add_argument("question")
    a.add_argument("--show", action="store_true", help="show each cited region with its highlight")
    a.add_argument("--save", action="store_true", help="file the answer back into the lake as an Analysis row")
    e = sub.add_parser("export", help="write the lake into a folder to submit, such as your shared Drive folder")
    e.add_argument("out", type=Path)
    sub.add_parser("history", help="list earlier questions, answers and citations")
    args = p.parse_args(argv)
    toml = args.config or KL.find_config()
    root = args.kdb or toml.absolute().parent / "kdb"
    name = "lake init" if args.cmd == "lake" else args.cmd
    try:
        if args.cmd == "history" or (args.cmd == "ask" and (args.show or args.save)):
            raise NotImplementedError("the SQLite history, --show and --save")
        if args.cmd == "lake":
            for line in KL.init(toml, root, args.team):
                print(line)
            print(f"the lake of {args.team} is ready")
        elif args.cmd == "export":
            print(f"exported to {export(KL.lake_config(toml), root, args.out)}")
        elif args.cmd == "ingest":
            return _ingest(toml, root, args)
        else:
            cfg = config.load(toml)
            guard.check(args.question, cfg.context)
            ctx = KL.open_context(toml, root, model=cfg.model)
            try:
                out = ask.answer(ask.make_agent(config.model_from(cfg), config.settings_from(cfg)), ctx, args.question)
            finally:
                ctx.lake.close()
            print(out.model_dump_json(indent=1))  # yours: print each claim with its paper, page and quote
    except NotImplementedError as e:
        print(f"kdb {name}: not written yet: {e}", file=sys.stderr)
        return 2
    except FileNotFoundError as e:
        if Path(e.filename or "") != toml:
            raise
        print(f"kdb {name}: there is no {toml}; copy kdb.toml.example to kdb.toml", file=sys.stderr)
        return 1
    except AgentRunError as e:  # the model gave up, ran out of retries or hit a usage limit
        print(f"kdb {name}: the model run failed: {e}", file=sys.stderr)
        return 1
    except (KL.LakeError, ExportError, Failed, config.ConfigError, guard.PromptTooLong, duckdb.Error) as e:
        print(f"kdb {name}: {e}", file=sys.stderr)
        return 1
    return 0


def _ingest(toml: Path, root: Path, args) -> int:
    cfg = config.load(toml)
    agent = ingest.make_agent(config.model_from(cfg), root, config.settings_from(cfg))
    ctx = KL.open_context(toml, root, model=cfg.model)
    try:
        done = ingest.ingest(ctx, args.pdf, agent, cfg.context, origin=args.origin)
    finally:
        ctx.lake.close()
    print(f"{len(done.facts)} facts, {len(done.rows)} rows written")
    for problem in done.checked.errors + done.checked.warnings:
        print(f"{problem.level} {problem.rule} {problem.path}: {problem.message}")
    return 1 if done.checked.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
