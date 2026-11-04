"""Command line entry point: ``ai4s <group> <command>``."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from . import __version__, adoption as adoption_mod, audit as audit_mod, ingest, ledger, naming, patrol, rename as rename_mod, selfcheck
from .bot import BotCore
from .registry import Registry, load_registry, scaffold


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _load_registry(args: argparse.Namespace) -> Registry:
    return load_registry(Path(args.registry), schema=naming.load_schema(getattr(args, "schema", None)))


def _print_issues(issues: List[naming.Issue], limit: int = 40) -> None:
    for issue in issues[:limit]:
        print(f"  {issue.severity:<5} {issue.code:<32} {issue.message}")
        if issue.hint:
            print(f"        -> {issue.hint}")
    if len(issues) > limit:
        print(f"  … {len(issues) - limit} more")


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------
def cmd_init(args: argparse.Namespace) -> int:
    dest = Path(args.dir).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    if (dest / "lab.yaml").exists() and not args.force:
        print(f"refusing to overwrite existing lab: {dest} (use --force)")
        return 2

    (dest / "spec").mkdir(parents=True, exist_ok=True)
    schema_src = naming.find_schema()
    shutil.copyfile(schema_src, dest / "spec" / "filename-schema.yaml")
    scaffold(dest / "registry", force=args.force)
    for sub in ("data", "derived", "index"):
        (dest / "library" / sub).mkdir(parents=True, exist_ok=True)
    ws = dest / "workspaces" / "owner-a"
    for sub in ("SR_DATA", "REGISTRY", "LIVEDOCS", "PERSONAL"):
        (ws / sub).mkdir(parents=True, exist_ok=True)
    (dest / "workspaces" / "steward" / "SR_DATA").mkdir(parents=True, exist_ok=True)

    lab = {
        "lab": {"name": dest.name, "timezone": "UTC"},
        "paths": {"library": "library", "registry": "registry", "workspaces": "workspaces"},
        "people": [
            {
                "id": "owner-a",
                "name": "Owner A",
                "role": "owner",
                "workspace": "workspaces/owner-a",
            },
            {
                "id": "steward",
                "name": "Steward",
                "role": "steward",
                "workspace": "workspaces/steward",
            },
        ],
        "policy": {"credential_max_age_days": 7},
        "bot": {"adapter": "console", "dry_run": True, "state_dir": "state", "steward": "steward"},
    }
    (dest / "lab.yaml").write_text(
        yaml.safe_dump(lab, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    print(f"created lab at {dest}")
    print("next:")
    print("  1. edit registry/{types,classes,codes}.yaml")
    print("  2. ai4s registry sign --registry registry --kind type --name MEAS --who 'Your Name' --date 2026-03-04 --apply")
    print("  3. put files in workspaces/owner-a/SR_DATA and run: ai4s check workspaces/owner-a/SR_DATA --registry registry")
    return 0


def cmd_init_demo(args: argparse.Namespace) -> int:
    from .demo import build

    dest = Path(args.dir).resolve()
    build(dest, force=args.force)
    print(f"demo lab built at {dest}")
    print(f"  ai4s check {dest / 'workspaces' / 'owner-a' / 'SR_DATA'} --registry {dest / 'registry'} --library {dest / 'library'}")
    print(f"  ai4s patrol --config {dest / 'lab.yaml'}")
    return 0


# ---------------------------------------------------------------------------
# naming
# ---------------------------------------------------------------------------
def cmd_naming_check(args: argparse.Namespace) -> int:
    reg = _load_registry(args) if args.registry else None
    parsed = naming.parse(
        args.name,
        registry=reg.as_mapping() if reg else None,
        schema=naming.load_schema(args.schema),
    )
    if args.json:
        print(json.dumps(parsed.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"name      : {parsed.raw}")
        if parsed.ok:
            print(
                f"identity  : R{parsed.batch:04d} / {parsed.sample} / {parsed.unit}"
            )
            print(f"type      : {parsed.type_code}  partition={parsed.partition}")
            print(f"conditions: {'_'.join(parsed.conditions) or 'NA'}")
            print(f"time      : {parsed.timestamp}  RUN{parsed.run:04d}  ext={parsed.ext}")
        for issue in parsed.issues:
            print(f"  ERROR {issue.code}: {issue.message}")
            if issue.hint:
                print(f"        -> {issue.hint}")
        for issue in parsed.warnings:
            print(f"  WARN  {issue.code}: {issue.message}")
    return 0 if parsed.ok else 1


def cmd_naming_selftest(args: argparse.Namespace) -> int:
    return naming.selftest(verbose=args.verbose)


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------
def cmd_registry_verify(args: argparse.Namespace) -> int:
    reg = _load_registry(args)
    result = reg.check()
    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        summary = reg.summary()
        print(
            "types  {total:>3} total / {approved:>3} approved / {proposed:>3} proposed / {deprecated:>3} deprecated".format(
                **summary["types"]
            )
        )
        print(
            "classes{total:>4} total / {approved:>3} approved / {proposed:>3} proposed / {deprecated:>3} deprecated".format(
                **summary["classes"]
            )
        )
        print(
            "codes  {total:>3} total / {approved:>3} approved / {proposed:>3} proposed / {deprecated:>3} deprecated".format(
                **summary["codes"]
            )
        )
        if result.errors:
            print("\nERRORS")
            _print_issues(result.errors)
        if result.warnings and args.verbose:
            print("\nWARNINGS")
            _print_issues(result.warnings)
        print(f"\nconclusion: {'OK' if result.ok else 'FAILED'}")
    return 0 if result.ok else 1


def cmd_registry_sign(args: argparse.Namespace) -> int:
    reg = _load_registry(args)
    actions = reg.sign(
        args.kind,
        args.name,
        who=args.who,
        on=args.date,
        note=args.note or "",
        apply=args.apply,
    )
    for action in actions:
        print(action)
    if not args.apply:
        print("\n(dry-run; add --apply to write signatures.yaml)")
    return 0


def cmd_registry_revoke(args: argparse.Namespace) -> int:
    reg = _load_registry(args)
    action = reg.revoke(
        args.kind, args.name, who=args.who, on=args.date, reason=args.reason, apply=args.apply
    )
    print(action)
    if not args.apply:
        print("(dry-run; add --apply to write signatures.yaml)")
    return 0


def cmd_registry_status(args: argparse.Namespace) -> int:
    reg = _load_registry(args)
    for kind, table in (("type", reg.types), ("class", reg.classes), ("code", reg.codes)):
        print(f"\n[{kind}]")
        for name, entry in table.items():
            state = entry.get("_signature_state", "missing")
            status = naming.effective_status(entry)
            extra = ""
            if entry.get("status") == "DEPRECATED":
                extra = f" superseded_by={entry.get('superseded_by') or '-'}"
            print(f"  {name:<16} {status:<16} signature={state}{extra}")
    return 0


# ---------------------------------------------------------------------------
# check / ingest
# ---------------------------------------------------------------------------
def cmd_check(args: argparse.Namespace) -> int:
    reg = _load_registry(args)
    manifest = ingest.manifest_sha_map(Path(args.library)) if args.library else None
    report = selfcheck.check_delivery(
        Path(args.path),
        reg,
        manifest=manifest,
        out_dir=Path(args.out) if args.out else None,
        write=not args.no_write,
        log_path=Path(args.log) if args.log else None,
        person=args.person,
        trigger=args.trigger,
    )
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(selfcheck.format_summary(report))
        print(f"snapshot: {report.snapshot_id}")
        if not args.no_write:
            print(f"wrote: {Path(args.out or args.path) / '_selfcheck_report.txt'}")
    if not report.ok:
        return 1
    if args.strict and report.warnings_answered < report.warnings_total:
        return 3
    return 0


def cmd_ingest_copy(args: argparse.Namespace) -> int:
    reg = _load_registry(args)
    result = ingest.copy(
        Path(args.path),
        Path(args.library),
        reg,
        apply=args.apply,
        batch=args.batch,
    )
    print(ingest.format_plan(result))
    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    if result.conflicts or result.invalid:
        return 1
    return 0


def cmd_ingest_verify(args: argparse.Namespace) -> int:
    result = ingest.verify(Path(args.library))
    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(
            f"checked {result.checked} rows: "
            f"missing={len(result.missing)} modified={len(result.modified)} "
            f"extra={len(result.extra)} bad_path={len(result.bad_path)}"
        )
        for label, rows in (
            ("missing", result.missing),
            ("modified", result.modified),
            ("extra", result.extra),
            ("bad_path", result.bad_path),
        ):
            for row in rows[:20]:
                print(f"  {label:<8} {row}")
        print(f"conclusion: {'OK' if result.ok else 'FAILED'}")
    return 0 if result.ok else 1


def cmd_ingest_void(args: argparse.Namespace) -> int:
    ingest.void(Path(args.library), args.name, args.reason, args.who)
    print(f"voided (file kept): {args.name}")
    return 0


# ---------------------------------------------------------------------------
# audit
# ---------------------------------------------------------------------------
def cmd_audit(args: argparse.Namespace) -> int:
    if bool(args.path) == bool(args.names):
        print("error: pass exactly one of <path> or --names <file>", file=sys.stderr)
        return 2
    schema = naming.load_schema(args.schema)
    registry = load_registry(Path(args.registry), schema=schema) if args.registry else None
    try:
        result = audit_mod.audit(
            Path(args.path) if args.path else None,
            registry=registry,
            schema=schema,
            label=args.label,
            top=args.top,
            names_file=Path(args.names) if args.names else None,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    report_path = None
    if not args.no_report:
        report_path = audit_mod.write_report(result, Path(args.out))
    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(audit_mod.format_summary(result))
        for idx, rec in enumerate(result.recommendations, 1):
            print(f"  {idx}. {rec}")
        if report_path:
            print(f"report: {report_path}")
    return 0


# ---------------------------------------------------------------------------
# rename
# ---------------------------------------------------------------------------
def cmd_rename(args: argparse.Namespace) -> int:
    reg = _load_registry(args)
    rows = rename_mod.load_plan(Path(args.plan))
    rows = rename_mod.build_plan(Path(args.root), rows, reg)
    result = rename_mod.apply_plan(
        Path(args.root),
        rows,
        log_path=Path(args.log) if args.log else None,
        dry_run=not args.apply,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(rename_mod.format_plan(rows))
        if args.apply and not result["rejected"]:
            print(f"renamed: {result['applied']}  log: {result['log']}")
        elif not args.apply:
            print("(dry-run; add --apply after the owner nods)")
    if result["rejected"]:
        return 1
    return 0


# ---------------------------------------------------------------------------
# adoption
# ---------------------------------------------------------------------------
def cmd_adoption(args: argparse.Namespace) -> int:
    report = adoption_mod.run(Path(args.config))
    out = (
        Path(args.out)
        if args.out
        else Path(args.config).resolve().parent / "state" / "adoption_report.md"
    )
    if not args.no_report:
        adoption_mod.write_report(report, out)
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(adoption_mod.format_summary(report))
        for person in report.people:
            print(
                f"  {person.name:<12} {person.status:<3} "
                f"M1={person.m1.date().isoformat() if person.m1 else '—'}  "
                f"rounds={person.rounds if person.rounds is not None else '—'}"
            )
        for warning in report.warnings:
            print(f"  warning: {warning}")
        if not args.no_report:
            print(f"report: {out}")
    return 0


# ---------------------------------------------------------------------------
# patrol / bot
# ---------------------------------------------------------------------------
def cmd_patrol(args: argparse.Namespace) -> int:
    data = patrol.run(Path(args.config))
    out = Path(args.out) if args.out else Path(args.config).resolve().parent / "state" / "patrol_last.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(patrol.format_report(data))
        print(f"\nwrote {out}")
    if args.strict and data["summary"]["blocked"]:
        return 1
    return 0


def cmd_bot_handle(args: argparse.Namespace) -> int:
    core = BotCore(Path(args.config), dry_run=True)
    reply = core.handle(args.sender, args.text)
    print(reply.text)
    return 0


def cmd_bot_receipt(args: argparse.Namespace) -> int:
    core = BotCore(Path(args.config))
    if args.questions:
        with Path(args.questions).open("r", encoding="utf-8") as fh:
            questions = yaml.safe_load(fh) or []
        if isinstance(questions, dict):
            questions = questions.get("questions", [])
    else:
        questions = [
            {"id": "1", "text": "凭据是本轮刚跑的吗？", "options": ["已做", "未做"]},
            {"id": "2", "text": "WARN 的答复都填了吗？", "options": ["已做", "未做"]},
        ]
    recipients = [x.strip() for x in (args.to or "").split(",") if x.strip()]
    if not recipients:
        print("--to is required (comma separated person ids)")
        return 2
    core.open_receipt(args.batch, questions, recipients)
    print(core.render_receipt(args.batch))
    return 0


def cmd_bot_receipt_show(args: argparse.Namespace) -> int:
    core = BotCore(Path(args.config))
    print(core.render_receipt(args.batch))
    return 0


def cmd_bot_serve(args: argparse.Namespace) -> int:
    from .adapters.feishu import FeishuAdapter

    core = BotCore(Path(args.config), dry_run=not args.live)
    adapter = FeishuAdapter(dry_run=not args.live)
    adapter.serve(core, host=args.host, port=args.port)
    return 0


def cmd_bot_brief(args: argparse.Namespace) -> int:
    print(BotCore(Path(args.config)).ai_brief())
    return 0


# ---------------------------------------------------------------------------
# ledger
# ---------------------------------------------------------------------------
def cmd_ledger_check(args: argparse.Namespace) -> int:
    issues = ledger.check(Path(args.file))
    errors = [i for i in issues if i.severity == "ERROR"]
    if args.json:
        print(
            json.dumps(
                {"ok": not errors, "issues": [i.to_dict() for i in issues]},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        _print_issues(issues)
        print(f"conclusion: {'OK' if not errors else 'FAILED'}")
    return 0 if not errors else 1


def cmd_ledger_query(args: argparse.Namespace) -> int:
    hits = ledger.query(Path(args.file), args.contains)
    for row in hits:
        print(f"{row.get('ext_id')}  [{row.get('status')}]  {row.get('claim')}")
        print(f"  -> {row.get('correction')}")
    print(f"\n{len(hits)} hit(s)")
    return 0


def cmd_ledger_report(args: argparse.Namespace) -> int:
    data = ledger.report(Path(args.file))
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai4s",
        description="AI4S data and knowledge governance toolkit",
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="group", required=True)

    # init
    p = sub.add_parser("init", help="scaffold a lab workspace")
    p.add_argument("--dir", default=".")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("init-demo", help="build a complete demo lab")
    p.add_argument("--dir", default="examples/demo")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_init_demo)

    # naming
    p = sub.add_parser("naming", help="parse and validate filenames")
    nsub = p.add_subparsers(dest="cmd", required=True)
    q = nsub.add_parser("check")
    q.add_argument("name")
    q.add_argument("--registry")
    q.add_argument("--schema")
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=cmd_naming_check)
    q = nsub.add_parser("selftest")
    q.add_argument("--verbose", action="store_true")
    q.set_defaults(func=cmd_naming_selftest)

    # registry
    p = sub.add_parser("registry", help="inspect, validate and sign the registry")
    rsub = p.add_subparsers(dest="cmd", required=True)
    q = rsub.add_parser("verify")
    q.add_argument("--registry", default="registry")
    q.add_argument("--schema")
    q.add_argument("--json", action="store_true")
    q.add_argument("--verbose", action="store_true")
    q.set_defaults(func=cmd_registry_verify)
    q = rsub.add_parser("status")
    q.add_argument("--registry", default="registry")
    q.add_argument("--schema")
    q.set_defaults(func=cmd_registry_status)
    q = rsub.add_parser("sign")
    q.add_argument("--registry", default="registry")
    q.add_argument("--schema")
    q.add_argument("--kind", choices=["type", "class", "code"], required=True)
    q.add_argument("--name", action="append", required=True)
    q.add_argument("--who", required=True)
    q.add_argument("--date", required=True)
    q.add_argument("--note", default="")
    q.add_argument("--apply", action="store_true")
    q.set_defaults(func=cmd_registry_sign)
    q = rsub.add_parser("revoke")
    q.add_argument("--registry", default="registry")
    q.add_argument("--schema")
    q.add_argument("--kind", choices=["type", "class", "code"], required=True)
    q.add_argument("--name", required=True)
    q.add_argument("--who", required=True)
    q.add_argument("--date", required=True)
    q.add_argument("--reason", required=True)
    q.add_argument("--apply", action="store_true")
    q.set_defaults(func=cmd_registry_revoke)

    # check
    p = sub.add_parser("check", help="pre-delivery self-check")
    p.add_argument("path")
    p.add_argument("--registry", default="registry")
    p.add_argument("--schema")
    p.add_argument("--library", default=None)
    p.add_argument("--out", default=None)
    p.add_argument("--no-write", action="store_true")
    p.add_argument("--strict", action="store_true", help="fail if WARN questions are unanswered")
    p.add_argument("--log", default=None, help="append a JSONL run record for adoption metrics")
    p.add_argument("--person", default=None, help="person id to record with --log")
    p.add_argument("--trigger", choices=["self", "steward", "ci"], default="self")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_check)

    # ingest
    p = sub.add_parser("ingest", help="copy-only ingest and verification")
    isub = p.add_subparsers(dest="cmd", required=True)
    q = isub.add_parser("copy")
    q.add_argument("path")
    q.add_argument("--library", required=True)
    q.add_argument("--registry", default="registry")
    q.add_argument("--schema")
    q.add_argument("--apply", action="store_true")
    q.add_argument("--batch", default=None)
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=cmd_ingest_copy)
    q = isub.add_parser("verify")
    q.add_argument("--library", required=True)
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=cmd_ingest_verify)
    q = isub.add_parser("void")
    q.add_argument("--library", required=True)
    q.add_argument("--name", required=True)
    q.add_argument("--reason", required=True)
    q.add_argument("--who", required=True)
    q.set_defaults(func=cmd_ingest_void)

    # audit
    p = sub.add_parser("audit", help="read-only lab data health check")
    p.add_argument("path", nargs="?", default=None)
    p.add_argument("--names", default=None, help="text file with one relative path per line")
    p.add_argument("--registry", default=None)
    p.add_argument("--schema")
    p.add_argument("--label", default=None, help="label to show instead of the real path")
    p.add_argument("--out", default="audit_report.md")
    p.add_argument("--no-report", action="store_true")
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_audit)

    # rename
    p = sub.add_parser("rename", help="guarded, all-or-nothing rename")
    p.add_argument("--root", required=True)
    p.add_argument("--plan", required=True, help="CSV with old,new[,确认改身份]")
    p.add_argument("--registry", default="registry")
    p.add_argument("--schema")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--log", default=None)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_rename)

    # adoption
    p = sub.add_parser("adoption", help="M1-M5 adoption report")
    p.add_argument("--config", required=True)
    p.add_argument("--out", default=None)
    p.add_argument("--no-report", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_adoption)

    # patrol
    p = sub.add_parser("patrol", help="read-only status snapshot")
    p.add_argument("--config", required=True)
    p.add_argument("--out", default=None)
    p.add_argument("--json", action="store_true")
    p.add_argument("--strict", action="store_true")
    p.set_defaults(func=cmd_patrol)

    # bot
    p = sub.add_parser("bot", help="receipt / release / waiver bot")
    bsub = p.add_subparsers(dest="cmd", required=True)
    q = bsub.add_parser("handle")
    q.add_argument("--config", required=True)
    q.add_argument("--sender", required=True)
    q.add_argument("text")
    q.set_defaults(func=cmd_bot_handle)
    q = bsub.add_parser("receipt")
    q.add_argument("--config", required=True)
    q.add_argument("--batch", required=True)
    q.add_argument("--questions", default=None)
    q.add_argument("--to", required=True)
    q.set_defaults(func=cmd_bot_receipt)
    q = bsub.add_parser("receipt-show")
    q.add_argument("--config", required=True)
    q.add_argument("--batch", required=True)
    q.set_defaults(func=cmd_bot_receipt_show)
    q = bsub.add_parser("serve")
    q.add_argument("--config", required=True)
    q.add_argument("--host", default="127.0.0.1")
    q.add_argument("--port", type=int, default=8080)
    q.add_argument("--live", action="store_true", help="actually send to Feishu")
    q.set_defaults(func=cmd_bot_serve)
    q = bsub.add_parser("brief")
    q.add_argument("--config", required=True)
    q.set_defaults(func=cmd_bot_brief)

    # ledger
    p = sub.add_parser("ledger", help="deprecation ledger")
    lsub = p.add_subparsers(dest="cmd", required=True)
    q = lsub.add_parser("check")
    q.add_argument("file")
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=cmd_ledger_check)
    q = lsub.add_parser("query")
    q.add_argument("file")
    q.add_argument("--contains", required=True)
    q.set_defaults(func=cmd_ledger_query)
    q = lsub.add_parser("report")
    q.add_argument("file")
    q.set_defaults(func=cmd_ledger_report)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
