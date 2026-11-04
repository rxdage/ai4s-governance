"""Copy-only ingest into a single-source library.

Design rules (see docs/03-intake.md):

* copy, never move;
* write the manifest row **immediately after each file lands** (a crash must not
  leave files on disk that the ledger does not know about);
* never overwrite: same name + different content is a conflict, not an update;
* content changes are re-ingested with the same ``T`` and ``RUN + 1``;
* nothing is ever deleted. A superseded file stays and is marked in a void
  ledger.
"""

from __future__ import annotations

import csv
import hashlib
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

import yaml

from . import naming
from .registry import Registry, is_forbidden_name

MANIFEST = "index/manifest.tsv"
VOID_LEDGER = "index/void_ledger.csv"


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def manifest_path(library: Path) -> Path:
    return Path(library) / MANIFEST


def read_manifest(library: Path) -> List[Dict[str, str]]:
    path = manifest_path(library)
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        return [dict(row) for row in reader]


def manifest_by_name(library: Path) -> Dict[str, Dict[str, str]]:
    out: Dict[str, Dict[str, str]] = {}
    for row in read_manifest(library):
        name = Path(row.get("sr_rel", "")).name
        if name:
            out[name] = row
    return out


def manifest_sha_map(library: Path) -> Dict[str, str]:
    return {
        name: row.get("sha256", "")
        for name, row in manifest_by_name(library).items()
        if row.get("sha256")
    }


def next_batch(library: Path, now: Optional[datetime] = None) -> str:
    now = now or datetime.now()
    prefix = now.strftime("%Y%m%d")
    used = set()
    for row in read_manifest(library):
        batch = row.get("ingest_batch", "")
        if batch.startswith(prefix + "-"):
            try:
                used.add(int(batch.split("-")[1]))
            except (IndexError, ValueError):
                pass
    n = 1
    while n in used:
        n += 1
    return f"{prefix}-{n:02d}"


@dataclass
class Item:
    src: Path
    name: str
    partition: str
    batch: int
    dest: Path
    size: int
    sha256: str
    status: str  # new | already | conflict | invalid
    detail: str = ""
    sidecar: Optional[Path] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "src": str(self.src),
            "name": self.name,
            "partition": self.partition,
            "dest": str(self.dest),
            "size": self.size,
            "sha256": self.sha256,
            "status": self.status,
            "detail": self.detail,
        }


@dataclass
class IngestResult:
    items: List[Item] = field(default_factory=list)
    copied: int = 0
    skipped: int = 0
    conflicts: int = 0
    invalid: int = 0
    batch: str = ""
    applied: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "batch": self.batch,
            "applied": self.applied,
            "copied": self.copied,
            "skipped": self.skipped,
            "conflicts": self.conflicts,
            "invalid": self.invalid,
            "items": [i.to_dict() for i in self.items],
        }


def _sidecar_of(path: Path, schema: Mapping[str, Any]) -> Optional[Path]:
    suffix = str(schema.get("derived", {}).get("suffix", ".meta.yaml"))
    candidate = path.with_name(path.name + suffix)
    return candidate if candidate.is_file() else None


def derived_problems(
    path: Path,
    schema: Mapping[str, Any],
    manifest_sha: Mapping[str, str],
) -> List[str]:
    """Return a list of ``CODE: message`` strings; empty means the gates pass."""
    problems: List[str] = []
    cfg = schema.get("derived", {})
    suffix = str(cfg.get("suffix", ".meta.yaml"))
    required = list(cfg.get("required_fields", []))
    methods = list(cfg.get("methods", []))
    forbidden = [
        str(x) for x in schema.get("registry", {}).get("forbidden_approvers", [])
    ]
    sidecar = path.with_name(path.name + suffix)
    if not sidecar.is_file():
        return ["SIDECAR_MISSING: 缺 " + sidecar.name]
    try:
        with sidecar.open("r", encoding="utf-8") as fh:
            meta = yaml.safe_load(fh) or {}
    except Exception as exc:  # noqa: BLE001
        return [f"SIDECAR_MISSING: 解析失败 {exc}"]
    if not isinstance(meta, dict):
        return ["SIDECAR_MISSING: 顶层必须是映射"]
    missing = [field for field in required if field not in meta]
    if missing:
        problems.append(f"SIDECAR_MISSING: 缺字段 {missing}")

    derived_from = meta.get("derived_from")
    if not isinstance(derived_from, list):
        derived_from = [derived_from] if derived_from else []
    input_sha = meta.get("input_sha256")
    if not isinstance(input_sha, list):
        input_sha = [input_sha] if input_sha else []
    if not derived_from:
        problems.append("DERIVED_INPUT_EMPTY: derived_from 为空")
    if derived_from and len(input_sha) != len(derived_from):
        problems.append("SIDECAR_MISSING: derived_from 与 input_sha256 数量不一致")

    method = str(meta.get("method", ""))
    if methods and method not in methods:
        problems.append(f"SIDECAR_MISSING: method={method!r} 不在 {methods}")
    if not str(meta.get("tool", "") or "").strip():
        problems.append("SIDECAR_MISSING: tool 为空")

    reviewer = str(meta.get("reviewed_by", "") or "").strip()
    if is_forbidden_name(reviewer, forbidden):
        problems.append(f"DERIVED_NOT_REVIEWED: reviewed_by={reviewer!r} 不是实名")

    for idx, source in enumerate(derived_from):
        name = Path(str(source)).name
        if name not in manifest_sha:
            problems.append(f"DERIVED_INPUT_NOT_IN_LIBRARY: {source}")
        elif idx < len(input_sha) and str(input_sha[idx]) != manifest_sha[name]:
            problems.append(f"DERIVED_INPUT_CHANGED: {source}")
    return problems


def plan(
    root: Path,
    library: Path,
    registry: Registry,
    schema: Optional[Mapping[str, Any]] = None,
) -> IngestResult:
    schema = schema or registry.schema
    root, library = Path(root), Path(library)
    reg_map = registry.as_mapping()
    existing = manifest_by_name(library)
    existing_sha = {name: row.get("sha256", "") for name, row in existing.items()}
    result = IngestResult(batch=next_batch(library))

    for path in sorted(_walk_delivery(root)):
        name = path.name
        if name.endswith(".meta.yaml"):
            continue
        parsed = naming.parse(name, registry=reg_map, schema=schema)
        if not parsed.ok or parsed.partition is None or parsed.batch is None:
            result.items.append(
                Item(
                    src=path,
                    name=name,
                    partition=parsed.partition or "",
                    batch=parsed.batch or 0,
                    dest=Path(""),
                    size=path.stat().st_size if path.exists() else 0,
                    sha256="",
                    status="invalid",
                    detail="; ".join(f"{i.code}: {i.message}" for i in parsed.errors)
                    or "cannot determine partition",
                )
            )
            result.invalid += 1
            continue

        dest = library / parsed.partition / f"R{parsed.batch:04d}" / name
        size = path.stat().st_size
        digest = sha256_file(path)
        if parsed.partition == "derived":
            problems = derived_problems(path, schema, existing_sha)
            if problems:
                result.items.append(
                    Item(
                        src=path,
                        name=name,
                        partition=parsed.partition,
                        batch=parsed.batch,
                        dest=dest,
                        size=size,
                        sha256=digest,
                        status="invalid",
                        detail="; ".join(problems),
                    )
                )
                result.invalid += 1
                continue
        status = "new"
        detail = ""
        row = existing.get(name)
        if dest.exists():
            if sha256_file(dest) == digest:
                status, detail = "already", "same name, same bytes"
            else:
                status, detail = "conflict", "same name, different bytes"
        elif row and row.get("sha256") == digest:
            status, detail = "already", "recorded in manifest, file present"
        elif row and row.get("sha256") != digest:
            status, detail = "conflict", "manifest has this name with another hash"

        if status == "already":
            result.skipped += 1
        elif status == "conflict":
            result.conflicts += 1

        result.items.append(
            Item(
                src=path,
                name=name,
                partition=parsed.partition,
                batch=parsed.batch,
                dest=dest,
                size=size,
                sha256=digest,
                status=status,
                detail=detail,
                sidecar=_sidecar_of(path, schema),
            )
        )
    return result


def _walk_delivery(root: Path) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d
            for d in dirnames
            if not d.startswith(("_", "~$", "."))
            and d not in {"__pycache__", ".git", ".venv", "node_modules"}
        ]
        for filename in filenames:
            if filename.startswith(("_", "~$", ".")):
                continue
            p = Path(dirpath) / filename
            if p.is_symlink():
                continue
            yield p


def copy(
    root: Path,
    library: Path,
    registry: Registry,
    schema: Optional[Mapping[str, Any]] = None,
    apply: bool = False,
    batch: Optional[str] = None,
) -> IngestResult:
    schema = schema or registry.schema
    result = plan(root, library, registry, schema)
    result.applied = apply
    result.batch = batch or result.batch
    if not apply:
        return result

    library = Path(library)
    manifest = manifest_path(library)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    new_file = not manifest.exists()
    with manifest.open("a", encoding="utf-8", newline="") as fh:
        if new_file:
            cols = schema.get("ingest", {}).get(
                "manifest_columns",
                ["sr_rel", "src_abs", "sha256", "size", "copied_at", "partition", "ingest_batch"],
            )
            fh.write("\t".join(cols) + "\n")

        for item in result.items:
            if item.status in {"invalid", "conflict"}:
                continue
            if item.status == "already":
                # the data file is in place; a sidecar may have been added later
                if item.sidecar and item.dest.exists():
                    side_dest = item.dest.with_name(item.dest.name + ".meta.yaml")
                    if not side_dest.exists():
                        side_dest.parent.mkdir(parents=True, exist_ok=True)
                        _atomic_copy(item.sidecar, side_dest, sha256_file(item.sidecar))
                        side_item = Item(
                            src=item.sidecar,
                            name=side_dest.name,
                            partition=item.partition,
                            batch=item.batch,
                            dest=side_dest,
                            size=side_dest.stat().st_size,
                            sha256=sha256_file(side_dest),
                            status="new",
                        )
                        _append_row(fh, library, side_item, result.batch)
                        result.copied += 1
                        fh.flush()
                        os.fsync(fh.fileno())
                continue
            item.dest.parent.mkdir(parents=True, exist_ok=True)
            _atomic_copy(item.src, item.dest, item.sha256)
            _append_row(fh, library, item, result.batch)
            result.copied += 1
            if item.sidecar:
                side_dest = item.dest.with_name(item.dest.name + ".meta.yaml")
                _atomic_copy(item.sidecar, side_dest, sha256_file(item.sidecar))
                side_item = Item(
                    src=item.sidecar,
                    name=side_dest.name,
                    partition=item.partition,
                    batch=item.batch,
                    dest=side_dest,
                    size=side_dest.stat().st_size,
                    sha256=sha256_file(side_dest),
                    status="new",
                )
                _append_row(fh, library, side_item, result.batch)
                result.copied += 1
            fh.flush()
            os.fsync(fh.fileno())
    return result


def _atomic_copy(src: Path, dest: Path, expected_sha: str) -> None:
    fd, tmp_name = tempfile.mkstemp(prefix=dest.name + ".", suffix=".tmp", dir=str(dest.parent))
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        shutil.copy2(src, tmp)
        got = sha256_file(tmp)
        if got != expected_sha:
            raise OSError(f"copy verification failed: {src} -> {dest}")
        os.replace(tmp, dest)
        try:
            os.chmod(dest, 0o444)
        except OSError:
            pass  # Windows / network shares may not support it
    finally:
        if tmp.exists():
            tmp.unlink()


def _append_row(fh, library: Path, item: Item, batch: str) -> None:
    rel = item.dest.relative_to(library).as_posix()
    row = [
        rel,
        str(item.src.resolve()),
        item.sha256,
        str(item.size),
        datetime.now().astimezone().isoformat(timespec="seconds"),
        item.partition,
        batch,
    ]
    fh.write("\t".join(row) + "\n")


@dataclass
class VerifyResult:
    checked: int = 0
    missing: List[str] = field(default_factory=list)
    modified: List[str] = field(default_factory=list)
    extra: List[str] = field(default_factory=list)
    bad_path: List[str] = field(default_factory=list)
    voided: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.missing or self.modified or self.extra or self.bad_path)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "checked": self.checked,
            "missing": self.missing,
            "modified": self.modified,
            "extra": self.extra,
            "bad_path": self.bad_path,
            "voided": self.voided,
        }


def verify(library: Path) -> VerifyResult:
    library = Path(library)
    res = VerifyResult()
    rows = read_manifest(library)
    known = set()
    for row in rows:
        rel = row.get("sr_rel", "")
        if not rel:
            continue
        known.add(rel)
        path = library / rel
        res.checked += 1
        if not path.is_file():
            res.missing.append(rel)
            continue
        size = path.stat().st_size
        if str(size) != str(row.get("size")):
            res.modified.append(f"{rel} (size {size} != {row.get('size')})")
            continue
        if sha256_file(path) != row.get("sha256"):
            res.modified.append(f"{rel} (sha256 mismatch)")
        parts = Path(rel).parts
        if len(parts) < 3 or parts[0] not in {"data", "derived"}:
            res.bad_path.append(rel)

    for path in library.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(library).as_posix()
        if rel.startswith("index/"):
            continue
        if rel not in known:
            res.extra.append(rel)

    void_file = library / VOID_LEDGER
    if void_file.is_file():
        with void_file.open("r", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                if row.get("file"):
                    res.voided.append(row["file"])
    return res


def void(library: Path, name: str, reason: str, who: str) -> None:
    """Mark a library file as void. Never deletes or moves it."""
    library = Path(library)
    path = library / VOID_LEDGER
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        if new:
            writer.writerow(["voided_at", "file", "reason", "who"])
        writer.writerow(
            [datetime.now().astimezone().isoformat(timespec="seconds"), name, reason, who]
        )


def format_plan(result: IngestResult, limit: int = 60) -> str:
    lines = [
        f"batch {result.batch}  {'APPLY' if result.applied else 'DRY-RUN'}",
        f"new={sum(1 for i in result.items if i.status == 'new')} "
        f"already={result.skipped} conflict={result.conflicts} invalid={result.invalid}",
    ]
    for item in result.items[:limit]:
        lines.append(f"  {item.status:<8} {item.partition:<7} {item.name}  {item.detail}")
    if len(result.items) > limit:
        lines.append(f"  … {len(result.items) - limit} more")
    if result.applied:
        lines.append(f"copied: {result.copied}")
    return "\n".join(lines)
