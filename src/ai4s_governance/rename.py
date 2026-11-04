"""Guarded rename: all-or-nothing, with the original name written to a log.

Five gates (see docs/01-naming.md §8):

1. the new name parses and every code is registered + signed;
2. the target does not exist (no overwrite);
3. no duplicate old/new names inside the plan;
4. the identity zone is unchanged, unless the row explicitly confirms it;
5. the extension is unchanged.

If any row fails, **nothing** is renamed.
"""

from __future__ import annotations

import csv
import hashlib
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from . import naming
from .registry import Registry

IDENTITY_RE = re.compile(r"^(R[0-9]{4}_(?:W[0-9]{4}|ALL)_(?:D[0-9]{4}|ALL))")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _identity(name: str) -> Optional[str]:
    m = IDENTITY_RE.match(name)
    return m.group(1) if m else None


def _extension(name: str) -> Optional[str]:
    if "." not in name:
        return None
    return name[name.index(".") :]


def _truthy(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "是", "确认"}


@dataclass
class Row:
    old: str
    new: str
    confirm_identity: bool = False
    reasons: List[str] = field(default_factory=list)
    src: Optional[Path] = None
    dst: Optional[Path] = None

    @property
    def ok(self) -> bool:
        return not self.reasons

    def to_dict(self) -> Dict[str, Any]:
        return {
            "old": self.old,
            "new": self.new,
            "ok": self.ok,
            "reasons": list(self.reasons),
        }


def load_plan(path: Path) -> List[Row]:
    rows: List[Row] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames or "old" not in reader.fieldnames or "new" not in reader.fieldnames:
            raise ValueError("plan CSV needs `old` and `new` columns")
        for raw in reader:
            old = (raw.get("old") or "").strip()
            new = (raw.get("new") or "").strip()
            if not old and not new:
                continue
            confirm = _truthy(raw.get("确认改身份") or raw.get("confirm_identity") or "")
            rows.append(Row(old=old, new=new, confirm_identity=confirm))
    return rows


def build_plan(
    root: Path,
    rows: Iterable[Row],
    registry: Registry,
    schema: Optional[Mapping[str, Any]] = None,
) -> List[Row]:
    schema = schema or registry.schema
    root = Path(root)
    rows = list(rows)
    old_seen: Dict[str, int] = {}
    new_seen: Dict[str, int] = {}
    for idx, row in enumerate(rows, 1):
        row.src = root / row.old
        row.dst = root / row.new
        if "/" in row.old or "\\" in row.old or "/" in row.new or "\\" in row.new:
            row.reasons.append("只允许文件名，不允许带路径")
            continue
        if row.old in old_seen:
            row.reasons.append(f"清单内旧名重复（与第 {old_seen[row.old]} 行）")
        old_seen[row.old] = idx
        if row.new in new_seen:
            row.reasons.append(f"清单内新名重复（与第 {new_seen[row.new]} 行）")
        new_seen[row.new] = idx

        if not row.src.is_file():
            row.reasons.append("源文件不存在")
            continue
        if row.dst.exists():
            row.reasons.append("目标已存在（拒绝覆盖）")

        parsed = naming.parse(row.new, registry=registry.as_mapping(), schema=schema)
        if not parsed.ok:
            row.reasons.extend(f"{issue.code}: {issue.message}" for issue in parsed.errors)

        old_identity, new_identity = _identity(row.old), _identity(row.new)
        if old_identity and new_identity and old_identity != new_identity:
            if not row.confirm_identity:
                row.reasons.append(
                    f"身份区变化 {old_identity} -> {new_identity}；确实要改在第三列写“是”"
                )

        old_ext, new_ext = _extension(row.old), _extension(row.new)
        if old_ext is None or new_ext is None:
            row.reasons.append("新旧名都必须有扩展名")
        elif old_ext != new_ext:
            row.reasons.append(f"扩展名变化 {old_ext} -> {new_ext}（改名不动内容）")
    return rows


def apply_plan(
    root: Path,
    rows: List[Row],
    log_path: Optional[Path] = None,
    dry_run: bool = True,
) -> Dict[str, Any]:
    root = Path(root)
    rejected = [row for row in rows if not row.ok]
    result: Dict[str, Any] = {
        "dry_run": dry_run,
        "planned": len(rows),
        "applied": 0,
        "rejected": len(rejected),
        "rows": [row.to_dict() for row in rows],
        "log": None,
    }
    if rejected:
        return result

    log_path = Path(log_path) if log_path else root / f"_rename_log_{datetime.now():%Y%m%d-%H%M%S}.csv"
    if dry_run:
        return result

    log_path.parent.mkdir(parents=True, exist_ok=True)
    new_log = not log_path.exists()
    with log_path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        if new_log:
            writer.writerow(["time", "dir", "old", "new", "bytes", "sha256", "result"])
        for row in rows:
            assert row.src and row.dst
            digest = sha256_file(row.src)
            size = row.src.stat().st_size
            try:
                row.src.rename(row.dst)
                outcome = "ok"
                result["applied"] += 1
            except OSError as exc:
                outcome = f"failed: {exc}"
            writer.writerow(
                [
                    datetime.now().astimezone().isoformat(timespec="seconds"),
                    str(row.src.parent),
                    row.old,
                    row.new,
                    size,
                    digest,
                    outcome,
                ]
            )
            fh.flush()
    result["log"] = str(log_path)
    return result


def format_plan(rows: List[Row], limit: int = 80) -> str:
    lines = [f"{len(rows)} row(s)"]
    for row in rows[:limit]:
        flag = "ok  " if row.ok else "FAIL"
        lines.append(f"  {flag} {row.old}")
        lines.append(f"       -> {row.new}")
        for reason in row.reasons:
            lines.append(f"          - {reason}")
    if len(rows) > limit:
        lines.append(f"  … {len(rows) - limit} more")
    rejected = sum(1 for row in rows if not row.ok)
    lines.append(f"rejected: {rejected} (all-or-nothing: {'WILL RENAME' if not rejected else 'NOTHING WILL CHANGE'})")
    return "\n".join(lines)
