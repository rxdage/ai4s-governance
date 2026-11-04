"""Deprecation ledger: machine-checkable memory of claims that did not survive.

A ledger entry is deliberately short and blunt:

* ``claim``      — the sentence people still repeat
* ``verdict``    — why it is wrong
* ``correction`` — what to say instead
* ``caveats``    — what *survives*; never throw away the surviving direction
* ``residue``    — files where the old value still lives (the sweep list)
* ``scope``      — required for "partially rehabilitated" entries
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

import yaml

from . import naming

REQUIRED = [
    "ext_id",
    "claim",
    "status",
    "date",
    "verdict",
    "correction",
    "caveats",
    "source",
]
STATUSES = {"作废", "更正", "部分平反", "void", "corrected", "partially-rehabilitated"}
ID_RE = re.compile(r"^DEP-[A-Z]{2,8}-[0-9]{1,4}$")


def load(path: Path) -> List[Dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    rows = data.get("deprecations", data if isinstance(data, list) else [])
    if not isinstance(rows, list):
        raise ValueError("ledger must be a list under `deprecations:`")
    return [r for r in rows if isinstance(r, dict)]


def check(path: Path) -> List[naming.Issue]:
    issues: List[naming.Issue] = []
    rows = load(path)
    seen: Dict[str, int] = {}
    for idx, row in enumerate(rows, 1):
        ext_id = str(row.get("ext_id", ""))
        missing = [f for f in REQUIRED if not row.get(f)]
        if missing:
            issues.append(
                naming.Issue(
                    "LEDGER_FIELD_MISSING",
                    "ERROR",
                    f"第 {idx} 条 {ext_id or '(no id)'} 缺字段：{missing}",
                )
            )
        if not ID_RE.match(ext_id):
            issues.append(
                naming.Issue(
                    "LEDGER_ID",
                    "ERROR",
                    f"第 {idx} 条 ext_id {ext_id!r} 不符合 DEP-<域>-<号>",
                )
            )
        if ext_id in seen:
            issues.append(
                naming.Issue(
                    "LEDGER_DUPLICATE",
                    "ERROR",
                    f"ext_id 重复：{ext_id}（第 {seen[ext_id]} 与第 {idx} 条）",
                )
            )
        seen[ext_id] = idx
        status = str(row.get("status", ""))
        if status not in STATUSES:
            issues.append(
                naming.Issue(
                    "LEDGER_STATUS",
                    "ERROR",
                    f"{ext_id} 的 status {status!r} 不在 {sorted(STATUSES)}",
                )
            )
        try:
            datetime.strptime(str(row.get("date", "")), "%Y-%m-%d")
        except ValueError:
            issues.append(
                naming.Issue("LEDGER_DATE", "ERROR", f"{ext_id} 的 date 必须是 YYYY-MM-DD")
            )
        residue = row.get("residue")
        if residue is not None and not isinstance(residue, list):
            issues.append(
                naming.Issue(
                    "LEDGER_RESIDUE", "ERROR", f"{ext_id} 的 residue 必须是列表"
                )
            )
        if status in {"部分平反", "partially-rehabilitated"} and not row.get("scope"):
            issues.append(
                naming.Issue(
                    "LEDGER_SCOPE",
                    "ERROR",
                    f"{ext_id} 是部分平反，必须写 scope（平反只对哪个范围成立）",
                )
            )
        caveats = str(row.get("caveats", ""))
        if caveats and not any(
            word in caveats for word in ("仍", "幸存", "不变", "成立", "survive", "still")
        ):
            issues.append(
                naming.Issue(
                    "LEDGER_CAVEAT",
                    "WARN",
                    f"{ext_id} 的 caveats 没写清“什么还站得住”",
                )
            )
    return issues


def query(path: Path, text: str) -> List[Dict[str, Any]]:
    needle = text.lower()
    hits = []
    for row in load(path):
        blob = " ".join(
            str(row.get(k, "")) for k in ("claim", "verdict", "correction", "caveats", "topics")
        ).lower()
        if needle in blob:
            hits.append(row)
    return hits


def report(path: Path) -> Dict[str, Any]:
    rows = load(path)
    by_status: Dict[str, int] = {}
    by_domain: Dict[str, int] = {}
    residue = 0
    for row in rows:
        by_status[str(row.get("status", "?"))] = by_status.get(str(row.get("status", "?")), 0) + 1
        m = re.match(r"^DEP-([A-Z]{2,8})-", str(row.get("ext_id", "")))
        domain = m.group(1) if m else "?"
        by_domain[domain] = by_domain.get(domain, 0) + 1
        residue += len(row.get("residue") or [])
    return {
        "entries": len(rows),
        "by_status": by_status,
        "by_domain": by_domain,
        "residue_files": residue,
    }
