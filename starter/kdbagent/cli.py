"""The kdb command: ingest, ask and history."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import ask, config, guard, ingest


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="kdb")
    p.add_argument("--kdb", type=Path, default=Path("kdb"), help="the kDB bundle")
    p.add_argument("--config", type=Path, default=Path("kdb.toml"))
    sub = p.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("ingest", help="add one paper to the kDB")
    i.add_argument("pdf", type=Path)
    a = sub.add_parser("ask", help="answer a question from the kDB")
    a.add_argument("question")
    a.add_argument("--show", action="store_true", help="show each cited region with its highlight")
    a.add_argument("--save", action="store_true", help="file the answer back into the kDB as an Analysis page")
    sub.add_parser("history", help="list earlier questions, answers and citations")
    args = p.parse_args(argv)
    try:
        if args.cmd == "history" or (args.cmd == "ask" and (args.show or args.save)):
            raise NotImplementedError("the SQLite history, --show and --save")
        cfg = config.load(args.config)
        if args.cmd == "ingest":
            facts = ingest.ingest(args.kdb, args.pdf, cfg)
            print(f"{len(facts)} facts")
        else:
            guard.check(args.question, cfg.context)
            out = ask.answer(ask.make_agent(config.model_from(cfg)), args.kdb, args.question)
            print(out.model_dump_json(indent=1))  # yours: print each claim with its paper, page and quote
    except NotImplementedError as e:
        print(f"kdb {args.cmd}: not written yet: {e}", file=sys.stderr)
        return 2
    except guard.PromptTooLong as e:
        print(f"kdb {args.cmd}: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
