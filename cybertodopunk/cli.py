"""Command line: list, check off, configure, convert.

    cybertodopunk                      the window
    cybertodopunk list [--json] [--company C | --all-companies] [--everyone] [--done]
    cybertodopunk done FILE ID [--at "YYYY-MM-DD HH:MM"]
    cybertodopunk start FILE ID | reopen FILE ID
    cybertodopunk switch COMPANY
    cybertodopunk config [show | name NAME | alias add|rm X | path add|rm DIR
                          | company add|rm NAME | team on|off]
    cybertodopunk new [DIR]            empty ACTIONS.tex in DIR (default .)
    cybertodopunk convert REPORT.tex... [--dry-run] [--input PATH]
    cybertodopunk check                parse every ACTIONS.tex found

SPDX-License-Identifier: Unlicense
"""

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__
from . import actions as act
from . import config as conf
from . import scan


def _fail(msg):
    print(f"cybertodopunk: {msg}", file=sys.stderr)
    return 1


def cmd_list(args, cfg):
    if args.all_companies:
        companies = cfg.companies
    else:
        companies = [args.company or cfg.active_company]
    groups, errors = scan.scan(cfg, everyone=args.everyone, include_done=args.done,
                               companies=companies)
    if args.json:
        json.dump(
            {
                "version": __version__,
                "user": cfg.full_name,
                "surname": scan.surname(cfg.full_name),
                "companies": cfg.companies,
                "active": cfg.active_company,
                "groups": [g.to_dict() for g in groups if g.tasks],
                "errors": errors,
            },
            sys.stdout,
            ensure_ascii=False,
        )
        sys.stdout.write("\n")
        return 0
    if not cfg.full_name and not args.everyone:
        print("No full name configured: cybertodopunk config name \"First LAST\"", file=sys.stderr)
    n = 0
    for g in groups:
        if not g.tasks:
            continue
        print(f"\n{g.cr_id}  ({len(g.tasks)})")
        for t in g.tasks:
            d = t.to_dict()
            sub = f"[{d['sub']}] " if d["sub"] else ""
            mark = {"todo": " ", "inprogress": ">", "done": "x"}[d["status"]]
            due = f"  due {d['due']}" if d["due"] not in ("", "–") else ""
            print(f"  [{mark}] {d['id']} {sub}{d['text']}  ({d['owner']}{due})")
            n += 1
    print(f"\n{n} action(s)" + (f", {len(errors)} file(s) unreadable" if errors else ""))
    for e in errors:
        print(f"  ! {e['file']}: {e['error']}", file=sys.stderr)
    return 1 if errors else 0


def cmd_status(args, cfg):
    try:
        if args.cmd == "done":
            a = act.complete(args.file, args.id, args.at)
            print(f"{args.id} done at {a.completed}")
        elif args.cmd == "start":
            act.start(args.file, args.id)
            print(f"{args.id} in progress")
        else:
            act.reopen(args.file, args.id)
            print(f"{args.id} reopened")
    except (OSError, act.ActionsError) as exc:
        return _fail(str(exc))
    return 0


def cmd_switch(args, cfg):
    match = [c for c in cfg.companies if c.upper() == args.company.upper()]
    if not match:
        return _fail(f"unknown company {args.company!r} (known: {', '.join(cfg.companies)})")
    cfg.active_company = match[0]
    conf.save(cfg)
    print(cfg.active_company)
    return 0


def _edit_list(lst, op, value):
    if op == "add" and value not in lst:
        lst.append(value)
    elif op == "rm":
        if value not in lst:
            raise KeyError(value)
        lst.remove(value)


def cmd_config(args, cfg):
    what = args.what or "show"
    try:
        if what == "show":
            d = cfg.to_dict()
            d["search_paths"] = cfg.search_paths
            d["surname"] = scan.surname(cfg.full_name)
            d["config_file"] = str(conf.config_path())
            print(json.dumps(d, indent=2, ensure_ascii=False))
            return 0
        if what == "name":
            cfg.full_name = " ".join(args.rest)
        elif what == "team":
            cfg.include_team = args.rest[:1] == ["on"]
        elif what in ("alias", "path", "company"):
            op, value = args.rest[0], " ".join(args.rest[1:])
            if op not in ("add", "rm") or not value:
                return _fail(f"usage: config {what} add|rm VALUE")
            if what == "path":
                value = str(Path(value).expanduser().resolve())
                if op == "add" and not os.path.isdir(value):
                    return _fail(f"{value} is not a directory")
            lst = {"alias": cfg.aliases, "path": cfg.extra_paths, "company": cfg.companies}[what]
            _edit_list(lst, op, value)
            if not cfg.companies:
                return _fail("at least one company is needed")
            if cfg.active_company not in cfg.companies:
                cfg.active_company = cfg.companies[0]
        else:
            return _fail(f"unknown config setting {what!r}")
    except (IndexError, KeyError) as exc:
        return _fail(f"config {what}: nothing to change ({exc})")
    conf.save(cfg)
    print(f"saved {conf.config_path()}")
    return 0


def cmd_new(args, cfg):
    path = Path(args.dir) / act.FILENAME
    try:
        act.write_new(path, [])
    except act.ActionsError as exc:
        return _fail(str(exc))
    print(path)
    return 0


def cmd_convert(args, cfg):
    from . import convert

    status = 0
    for tex in args.reports:
        try:
            out, items = convert.convert(tex, input_path=args.input, dry_run=args.dry_run)
        except (OSError, convert.ConvertError, act.ActionsError) as exc:
            print(f"SKIP {tex}: {exc}", file=sys.stderr)
            status = 1
            continue
        verb = "would write" if args.dry_run else "wrote"
        print(f"{tex}: {verb} {out} ({len(items)} actions)")
    return status


def cmd_check(args, cfg):
    bad = 0
    files = list(scan.find_action_files(args.paths or cfg.search_paths))
    for f in files:
        try:
            n = len(act.parse_file(f))
            print(f"ok   {f} ({n})")
        except (OSError, UnicodeDecodeError, act.ActionsError) as exc:
            print(f"FAIL {f}: {exc}")
            bad += 1
    print(f"{len(files)} file(s), {bad} with errors")
    return 1 if bad else 0


def build_parser():
    p = argparse.ArgumentParser(prog="cybertodopunk", description="Meeting actions from ACTIONS.tex files.")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="cmd")

    s = sub.add_parser("list", help="list my open actions")
    s.add_argument("--json", action="store_true")
    s.add_argument("--company")
    s.add_argument("--all-companies", action="store_true")
    s.add_argument("--everyone", action="store_true", help="every owner, not only me")
    s.add_argument("--done", action="store_true", help="include completed actions")

    for name, help_ in (("done", "check an action off (writes the time)"),
                        ("start", "mark an action in progress"),
                        ("reopen", "undo: mark an action to do again")):
        s = sub.add_parser(name, help=help_)
        s.add_argument("file")
        s.add_argument("id")
        if name == "done":
            s.add_argument("--at", help='completion time, "YYYY-MM-DD HH:MM" (default: now)')

    s = sub.add_parser("switch", help="set the active company")
    s.add_argument("company")

    s = sub.add_parser("config", help="show or change the settings")
    s.add_argument("what", nargs="?")
    s.add_argument("rest", nargs="*")

    s = sub.add_parser("new", help="write an empty ACTIONS.tex")
    s.add_argument("dir", nargs="?", default=".")

    s = sub.add_parser("convert", help="move a report's action table into ACTIONS.tex")
    s.add_argument("reports", nargs="+")
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--input", default="ACTIONS", help="argument of \\input (default: ACTIONS)")

    s = sub.add_parser("check", help="parse every ACTIONS.tex")
    s.add_argument("paths", nargs="*")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.cmd is None:
        from .app import main as gui

        return gui([])
    cfg = conf.load()
    handler = {
        "list": cmd_list, "done": cmd_status, "start": cmd_status, "reopen": cmd_status,
        "switch": cmd_switch, "config": cmd_config, "new": cmd_new,
        "convert": cmd_convert, "check": cmd_check,
    }[args.cmd]
    return handler(args, cfg)
