"""Adoption metrics: did people actually start using the system?

Five milestones:

* M1 first PASS (a credential)
* M2 first PASS on a second day (habit, not a one-off)
* M3 first receipt reply
* M4 first registry proposal
* M5 first time the person explains a rule to someone else (manual; not machine-detectable)

The tool reads `state/selfcheck_runs.jsonl` (written by `ai4s check --log`),
`state/tickets.jsonl` (written by the bot), and each workspace's `REGISTRY/`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any, Dict, Iterable, List, Mapping, Optional

import yaml

from .patrol import load_lab, resolve

RUN_LOG = Path("state") / "selfcheck_runs.jsonl"
TICKETS = Path("state") / "tickets.jsonl"
PROPOSAL_DIR = "REGISTRY"


def _parse_ts(value: Any) -> Optional[datetime]:
    if not value:
        return None
    text = str(value)
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        dt = None
    if dt is None:
        for fmt in ("%Y-%m-%d %H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt


def _parse_date(value: Any) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _as_date(dt: datetime) -> date:
    return dt.date()


@dataclass
class PersonAdoption:
    id: str
    name: str
    role: str
    first_run: Optional[datetime] = None
    m1: Optional[datetime] = None
    m1_source: str = "none"
    rounds: Optional[int] = None
    days_to_first_pass: Optional[float] = None
    m2: Optional[datetime] = None
    m3: Optional[datetime] = None
    m4: Optional[datetime] = None
    last_activity: Optional[datetime] = None
    status: str = "M0"
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        def fmt(value: Optional[datetime]) -> Optional[str]:
            return value.isoformat(timespec="seconds") if value else None

        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "first_run": fmt(self.first_run),
            "m1": fmt(self.m1),
            "m1_source": self.m1_source,
            "rounds": self.rounds,
            "days_to_first_pass": self.days_to_first_pass,
            "m2": fmt(self.m2),
            "m3": fmt(self.m3),
            "m4": fmt(self.m4),
            "last_activity": fmt(self.last_activity),
            "status": self.status,
            "notes": self.notes,
        }


@dataclass
class AdoptionReport:
    lab: str
    generated_at: str
    people: List[PersonAdoption] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    log_path: str = ""
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lab": self.lab,
            "generated_at": self.generated_at,
            "log_path": self.log_path,
            "summary": self.summary,
            "warnings": self.warnings,
            "people": [p.to_dict() for p in self.people],
        }


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _first_proposal(workspace: Path) -> Optional[datetime]:
    folder = workspace / PROPOSAL_DIR
    if not folder.is_dir():
        return None
    dates: List[date] = []
    for path in sorted(folder.glob("*.yaml")):
        try:
            with path.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        for kind in ("types", "classes", "codes"):
            table = data.get(kind) or {}
            if not isinstance(table, dict):
                continue
            for entry in table.values():
                if not isinstance(entry, dict):
                    continue
                parsed = _parse_date(entry.get("proposed_at"))
                if parsed:
                    dates.append(parsed)
    if not dates:
        return None
    return datetime.combine(min(dates), time.min).astimezone()


def _credential_time(workspace: Path) -> Optional[datetime]:
    path = workspace / "SR_DATA" / "_credential.txt"
    if not path.is_file():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime).astimezone()


def _infer_person(root: str, people: Mapping[str, Path]) -> str:
    text = str(root)
    for person, ws in people.items():
        if text.startswith(str(ws)):
            return person
    return ""


def run(config_path: Path) -> AdoptionReport:
    cfg_path = Path(config_path).resolve()
    base = cfg_path.parent
    cfg = load_lab(cfg_path)
    bot_cfg = cfg.get("bot", {}) or {}
    state_dir = resolve(base, str(bot_cfg.get("state_dir", "state")))
    log_path = state_dir / "selfcheck_runs.jsonl"
    tickets_path = state_dir / "tickets.jsonl"

    people_cfg = {
        str(p.get("id")): p for p in cfg.get("people", []) if p.get("id")
    }
    workspaces = {
        pid: resolve(base, str(p.get("workspace", ""))) for pid, p in people_cfg.items()
    }

    runs = _read_jsonl(log_path)
    tickets = _read_jsonl(tickets_path)
    report = AdoptionReport(
        lab=str(cfg.get("lab", {}).get("name", cfg_path.stem)),
        generated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        log_path=str(log_path.relative_to(base)) if log_path.is_relative_to(base) else str(log_path),
    )
    if not runs:
        report.warnings.append(
            "no self-check log yet; run `ai4s check ... --log <state>/selfcheck_runs.jsonl --person <id>`"
        )

    by_person: Dict[str, List[Dict[str, Any]]] = {}
    for row in runs:
        person = str(row.get("person") or "")
        if not person:
            person = _infer_person(str(row.get("root", "")), workspaces)
        if person:
            by_person.setdefault(person, []).append(row)

    receipts: Dict[str, datetime] = {}
    for ticket in tickets:
        if ticket.get("type") != "receipt":
            continue
        person = str(ticket.get("person") or "")
        at = _parse_ts(ticket.get("at"))
        if person and at and (person not in receipts or at < receipts[person]):
            receipts[person] = at

    for pid, person_cfg in people_cfg.items():
        ws = workspaces[pid]
        rows = sorted(
            by_person.get(pid, []),
            key=lambda r: _parse_ts(r.get("at")) or datetime(1970, 1, 1, tzinfo=timezone.utc),
        )
        timed = [(row, _parse_ts(row.get("at"))) for row in rows]
        timed = [(row, at) for row, at in timed if at is not None]

        status = PersonAdoption(
            id=pid,
            name=str(person_cfg.get("name", pid)),
            role=str(person_cfg.get("role", "owner")),
        )
        if timed:
            status.first_run = timed[0][1]
            pass_runs = [(row, at) for row, at in timed if bool(row.get("ok"))]
            if pass_runs:
                status.m1 = pass_runs[0][1]
                status.m1_source = "log"
                status.rounds = timed.index(pass_runs[0]) + 1
                if status.first_run:
                    delta = status.m1 - status.first_run
                    status.days_to_first_pass = round(delta.total_seconds() / 86400, 2)
                first_day = _as_date(status.m1)
                for _, at in pass_runs:
                    if _as_date(at) > first_day:
                        status.m2 = at
                        break
            else:
                status.notes.append("no PASS yet")
        else:
            credential = _credential_time(ws)
            if credential:
                status.m1 = credential
                status.m1_source = "credential-mtime"
                status.notes.append(
                    "no run log; M1 uses the latest credential mtime (rounds/days unavailable)"
                )
            else:
                status.notes.append("no runs and no credential")

        status.m3 = receipts.get(pid)
        status.m4 = _first_proposal(ws)
        dates = [d for d in (status.first_run, status.m1, status.m2, status.m3, status.m4) if d]
        status.last_activity = max(dates) if dates else None
        if status.m4:
            status.status = "M4"
        elif status.m3:
            status.status = "M3"
        elif status.m2:
            status.status = "M2"
        elif status.m1:
            status.status = "M1"
        report.people.append(status)

    m1_people = [p for p in report.people if p.m1]
    days = [p.days_to_first_pass for p in report.people if p.days_to_first_pass is not None]
    rounds = [p.rounds for p in report.people if p.rounds is not None]
    active_cutoff = datetime.now().astimezone() - timedelta(days=30)
    report.summary = {
        "people": len(report.people),
        "m1": len(m1_people),
        "m2": sum(1 for p in report.people if p.m2),
        "m3": sum(1 for p in report.people if p.m3),
        "m4": sum(1 for p in report.people if p.m4),
        "median_days_to_first_pass": round(median(days), 2) if days else None,
        "median_rounds_to_first_pass": int(median(rounds)) if rounds else None,
        "active_last_30d": sum(
            1 for p in report.people if p.last_activity and p.last_activity >= active_cutoff
        ),
    }
    return report


def _fmt(value: Optional[datetime]) -> str:
    return value.strftime("%Y-%m-%d") if value else "—"


def _fmt_days(value: Optional[float]) -> str:
    if value is None:
        return "—"
    if value < 1:
        return f"{value * 24:.1f} h"
    return f"{value:.1f} d"


def render_markdown(report: AdoptionReport) -> str:
    lines = [
        "# Adoption report",
        "",
        f"- **Lab:** {report.lab}",
        f"- **Generated:** {report.generated_at}",
        f"- **Run log:** `{report.log_path}`",
        "",
    ]
    if report.warnings:
        lines.append("## Warnings")
        lines.append("")
        for warning in report.warnings:
            lines.append(f"- {warning}")
        lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---:|")
    labels = {
        "people": "People",
        "m1": "M1 first PASS",
        "m2": "M2 second day",
        "m3": "M3 receipt",
        "m4": "M4 proposal",
        "median_days_to_first_pass": "Median days to first PASS",
        "median_rounds_to_first_pass": "Median rounds to first PASS",
        "active_last_30d": "Active in last 30 days",
    }
    for key, value in report.summary.items():
        lines.append(f"| {labels.get(key, key)} | {value if value is not None else '—'} |")
    lines.append("")
    lines.append("## Per person")
    lines.append("")
    lines.append("| Person | Status | M1 first PASS | Days to M1 | Rounds | M2 second day | M3 receipt | M4 proposal | Last activity |")
    lines.append("|---|---|---|---:|---:|---|---|---|---|")
    for p in report.people:
        lines.append(
            "| {name} | {status} | {m1} | {days} | {rounds} | {m2} | {m3} | {m4} | {last} |".format(
                name=p.name,
                status=p.status,
                m1=_fmt(p.m1),
                days=_fmt_days(p.days_to_first_pass),
                rounds=p.rounds if p.rounds is not None else "—",
                m2=_fmt(p.m2),
                m3=_fmt(p.m3),
                m4=_fmt(p.m4),
                last=_fmt(p.last_activity),
            )
        )
    lines.append("")
    lines.append("## How to read this")
    lines.append("")
    lines.append("- **M1** — first PASS: a `_credential.txt` exists or the run log has `ok=true`.")
    lines.append("- **M2** — first PASS on a second calendar day: habit, not a one-off.")
    lines.append("- **M3** — first receipt reply recorded by the bot.")
    lines.append("- **M4** — first registry proposal (`proposed_at` in `REGISTRY/*.yaml`).")
    lines.append("- **M5** — first time the person explains a rule to someone else. Manual; this tool can't see it.")
    lines.append("")
    lines.append("## What to do next")
    lines.append("")
    stalled = [p for p in report.people if not p.m1 and p.role != "steward"]
    if stalled:
        lines.append("- No PASS yet: " + ", ".join(p.name for p in stalled) + ". Pair them with a champion for 15 minutes.")
    slow = [p for p in report.people if p.role != "steward" and p.rounds and p.rounds > 3]
    if slow:
        lines.append("- More than 3 rounds to first PASS: " + ", ".join(p.name for p in slow) + ". Improve the error messages, not the person.")
    if report.summary.get("m3", 0) == 0:
        lines.append("- No receipts yet: the loop is not closed. Send one receipt card and watch the reply.")
    if not stalled and not slow and report.summary.get("m3"):
        lines.append("- The loop is running. Next: measure new-hire time to first PASS.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("Generated by `ai4s adoption` (ai4s-governance). No files were modified.")
    return "\n".join(lines) + "\n"


def write_report(report: AdoptionReport, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(report), encoding="utf-8")
    return path


def format_summary(report: AdoptionReport) -> str:
    s = report.summary
    return (
        f"{s['people']} people, M1={s['m1']}, M2={s['m2']}, M3={s['m3']}, M4={s['m4']}; "
        f"median days to first PASS={s['median_days_to_first_pass']}, "
        f"median rounds={s['median_rounds_to_first_pass']}"
    )
