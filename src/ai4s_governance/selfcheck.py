"""Pre-delivery self-check: the gate that a human does not have to trust.

The rule that matters most: **the program decides PASS, not the AI.** An agent
may run this tool, read the report and fix filenames, but it may not edit the
checker, the schema or the registry snapshot to make the check pass.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import yaml

from . import naming
from .registry import Registry, is_forbidden_name

TEXT_EXTS = {
    ".csv",
    ".tsv",
    ".txt",
    ".json",
    ".md",
    ".yaml",
    ".yml",
    ".log",
    ".dat",
}
IDENTITY_RE = re.compile(r"R(\d{4})_(W(\d{4}|ALL))_(D(\d{4}|ALL))")
SKIP_PREFIXES = ("_", "~$", ".")


# ---------------------------------------------------------------------------
# data model
# ---------------------------------------------------------------------------
@dataclass
class Finding:
    code: str
    severity: str
    subject: str
    message: str
    hint: str = ""
    who: str = "owner-only"

    def to_dict(self) -> Dict[str, str]:
        return {
            "code": self.code,
            "severity": self.severity,
            "subject": self.subject,
            "message": self.message,
            "hint": self.hint,
            "who": self.who,
        }


@dataclass
class CheckReport:
    root: Path
    generated_at: str
    files: int = 0
    bytes: int = 0
    findings: List[Finding] = field(default_factory=list)
    warnings_answered: int = 0
    warnings_total: int = 0
    snapshot_id: str = ""
    registry_summary: Dict[str, Any] = field(default_factory=dict)

    @property
    def errors(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == "ERROR"]

    @property
    def warnings(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == "WARN"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> Dict[str, Any]:
        return {
            "root": str(self.root),
            "generated_at": self.generated_at,
            "files": self.files,
            "bytes": self.bytes,
            "ok": self.ok,
            "errors": len(self.errors),
            "warnings": len(self.warnings),
            "warnings_answered": self.warnings_answered,
            "snapshot_id": self.snapshot_id,
            "findings": [f.to_dict() for f in self.findings],
        }


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _now() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S%z")


def _iter_files(root: Path) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d
            for d in dirnames
            if not d.startswith(SKIP_PREFIXES)
            and d not in {"__pycache__", ".git", ".venv", "node_modules"}
        ]
        for filename in filenames:
            if filename.startswith(SKIP_PREFIXES):
                continue
            if filename.endswith((".pyc", ".pyo")):
                continue
            yield Path(dirpath) / filename


def _is_text(path: Path) -> bool:
    return path.suffix.lower() in TEXT_EXTS


def _read_head(path: Path, limit: int = 8192) -> str:
    try:
        with path.open("rb") as fh:
            raw = fh.read(limit)
        return raw.decode("utf-8", errors="ignore")
    except OSError:
        return ""


def registry_fingerprint(reg: Registry) -> str:
    payload = {
        "types": {k: v for k, v in reg.types.items()},
        "classes": {k: v for k, v in reg.classes.items()},
        "codes": {k: v for k, v in reg.codes.items()},
        "signatures": reg.signatures,
        "classification": reg.classification,
    }
    clean = {
        key: {
            name: {k: v for k, v in entry.items() if not str(k).startswith("_")}
            if isinstance(entry, dict)
            else entry
            for name, entry in table.items()
        }
        if isinstance(table, dict)
        else table
        for key, table in payload.items()
    }
    blob = yaml.safe_dump(clean, allow_unicode=True, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _load_answers(path: Path) -> Dict[Tuple[str, str], Dict[str, str]]:
    out: Dict[Tuple[str, str], Dict[str, str]] = {}
    if not path.is_file():
        return out
    with path.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            key = (row.get("category", ""), row.get("subject", ""))
            out[key] = row
    return out


def _normalize_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


# ---------------------------------------------------------------------------
# the check
# ---------------------------------------------------------------------------
def check_delivery(
    root: Path,
    registry: Registry,
    schema: Optional[Mapping[str, Any]] = None,
    manifest: Optional[Mapping[str, str]] = None,
    out_dir: Optional[Path] = None,
    write: bool = True,
    log_path: Optional[Path] = None,
    person: Optional[str] = None,
    trigger: str = "self",
) -> CheckReport:
    root = Path(root)
    schema = schema or registry.schema
    report = CheckReport(root=root, generated_at=_now(), snapshot_id=registry_fingerprint(registry))
    report.registry_summary = registry.summary()
    if not root.is_dir():
        report.findings.append(
            Finding("ENV_ROOT_MISSING", "ERROR", str(root), "交付根不存在")
        )
        return report

    reg_map = registry.as_mapping()
    manifest = manifest or {}
    by_name: Dict[str, List[Path]] = {}
    seen: Dict[str, naming.ParsedName] = {}
    run_groups: Dict[Tuple[str, str, Tuple[str, ...]], List[int]] = {}
    ts_groups: Dict[str, List[str]] = {}
    empty_dirs: List[str] = []

    for dirpath, dirnames, filenames in os.walk(root):
        if not dirnames and not filenames and Path(dirpath) != root:
            empty_dirs.append(str(Path(dirpath).relative_to(root)))

    for path in sorted(_iter_files(root)):
        rel = str(path.relative_to(root))
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        report.files += 1
        report.bytes += size

        name = path.name
        by_name.setdefault(name, []).append(path)
        if name.endswith(".meta.yaml"):
            base = path.with_name(name[: -len(".meta.yaml")])
            if not base.is_file():
                report.findings.append(
                    Finding(
                        "SIDECAR_MISSING",
                        "WARN",
                        rel,
                        "sidecar 找不到对应的数据文件",
                        "sidecar 必须和它的数据文件同目录、同前缀",
                    )
                )
            continue
        parsed = naming.parse(name, registry=reg_map, schema=schema)
        seen[name] = parsed

        for issue in parsed.issues:
            report.findings.append(
                Finding(
                    code=issue.code,
                    severity=issue.severity,
                    subject=rel,
                    message=issue.message,
                    hint=issue.hint,
                    who="owner-only",
                )
            )
        for issue in parsed.warnings:
            report.findings.append(
                Finding(
                    code=issue.code,
                    severity="WARN",
                    subject=rel,
                    message=issue.message,
                    hint=issue.hint,
                    who="ai-fixable-with-approval"
                    if issue.code == "COND_ORDER"
                    else "owner-only",
                )
            )

        if parsed.ok and parsed.batch is not None:
            key = (str(parsed.batch), str(parsed.type_code), tuple(parsed.conditions))
            if parsed.run is not None:
                run_groups.setdefault(key, []).append(parsed.run)
            if parsed.timestamp:
                ts_groups.setdefault(parsed.timestamp, []).append(rel)

        # content cross-check (WARN only: the human decides which side is right)
        if _is_text(path):
            head = _read_head(path)
            found = {
                (f"R{m.group(1)}", f"W{m.group(3)}" if m.group(3) != "ALL" else "ALL",
                 f"D{m.group(5)}" if m.group(5) != "ALL" else "ALL")
                for m in IDENTITY_RE.finditer(head)
            }
            if found and parsed.batch is not None:
                expected = [f"R{parsed.batch:04d}"]
                if parsed.sample and parsed.sample != "ALL":
                    expected.append(parsed.sample)
                if parsed.unit and parsed.unit != "ALL":
                    expected.append(parsed.unit)
                if not any(list(token[: len(expected)]) == expected for token in found):
                    report.findings.append(
                        Finding(
                            "CONTENT_ID_MISMATCH",
                            "WARN",
                            rel,
                            f"内容里出现的身份号是 {sorted('_'.join(t) for t in found)}，"
                            f"文件名是 {'_'.join(expected)}",
                            "先问本人哪边是对的，不许为了消错去改内容或文件名",
                            who="owner-only",
                        )
                    )

        # derived-data gates
        if parsed.ok and parsed.partition == "derived":
            _check_derived(report, path, rel, registry, schema, manifest)

    # duplicates
    for name, paths in by_name.items():
        if len(paths) > 1:
            for p in paths:
                report.findings.append(
                    Finding(
                        "NAME_DUPLICATE",
                        "ERROR",
                        str(p.relative_to(root)),
                        f"完整文件名在交付范围内出现 {len(paths)} 次",
                        "库内唯一是硬约束；先查是不是重复拷贝，再决定保留哪一份",
                    )
                )

    # RUN gaps
    for (batch, type_code, conditions), runs in sorted(run_groups.items()):
        runs = sorted(set(runs))
        if not runs:
            continue
        expected = set(range(0, runs[-1] + 1))
        missing = sorted(expected - set(runs))
        if missing:
            shown = ", ".join(f"RUN{m:04d}" for m in missing[:10])
            more = f" 等 {len(missing)} 个" if len(missing) > 10 else ""
            report.findings.append(
                Finding(
                    "RUN_GAP",
                    "WARN",
                    f"R{batch}_...__{type_code}__{'_'.join(conditions) or 'NA'}",
                    f"RUN 断号：{shown}{more}",
                    "问本人：丢了 / 漏传了 / 有意不交？答案进台账，不是替他补一个号",
                )
            )

    # timestamp clusters
    for ts, files in sorted(ts_groups.items()):
        if len(files) >= 3:
            report.findings.append(
                Finding(
                    "TIMESTAMP_CLUSTER",
                    "WARN",
                    f"T{ts}",
                    f"{len(files)} 个文件共用同一时间戳",
                    "问本人：T 是真实采集时间，还是改名当天填的？",
                )
            )

    for d in empty_dirs:
        report.findings.append(
            Finding("EMPTY_DIR", "WARN", d, "空目录", "可能只是漏传；不要自动删除")
        )

    # merge prior answers
    out_dir = Path(out_dir) if out_dir else root
    prior = _load_answers(out_dir / "_pending.csv")
    for f in report.findings:
        if f.severity == "WARN":
            key = (f.code, f.subject)
            f_answer = prior.get(key, {})
            setattr(f, "_answer", f_answer.get("answer", ""))
    report.warnings_total = len(report.warnings)
    report.warnings_answered = sum(
        1 for f in report.warnings if getattr(f, "_answer", "").strip()
    )

    if write:
        _write_outputs(report, out_dir, prior)
    if log_path:
        _append_run_log(report, Path(log_path), person=person, trigger=trigger)
    return report


def _append_run_log(
    report: CheckReport,
    log_path: Path,
    person: Optional[str],
    trigger: str,
) -> None:
    """Append one JSONL row per self-check run; used for adoption metrics."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "at": report.generated_at,
        "person": person or "",
        "trigger": trigger,
        "root": str(report.root.resolve()),
        "files": report.files,
        "errors": len(report.errors),
        "warnings": report.warnings_total,
        "answered": report.warnings_answered,
        "ok": report.ok,
        "snapshot": report.snapshot_id,
    }
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _check_derived(
    report: CheckReport,
    path: Path,
    rel: str,
    registry: Registry,
    schema: Mapping[str, Any],
    manifest: Mapping[str, str],
) -> None:
    cfg = schema.get("derived", {})
    suffix = str(cfg.get("suffix", ".meta.yaml"))
    required = list(cfg.get("required_fields", []))
    methods = list(cfg.get("methods", []))
    forbidden = [
        str(x)
        for x in schema.get("registry", {}).get("forbidden_approvers", [])
    ]

    sidecar = path.with_name(path.name + suffix)
    if not sidecar.is_file():
        report.findings.append(
            Finding(
                "SIDECAR_MISSING",
                "ERROR",
                rel,
                f"衍生文件缺 sidecar：{path.name}{suffix}",
                "sidecar 必须和它描述的数据文件放在同一目录",
            )
        )
        return

    try:
        with sidecar.open("r", encoding="utf-8") as fh:
            meta = yaml.safe_load(fh) or {}
    except Exception as exc:  # noqa: BLE001 - report, don't crash the gate
        report.findings.append(
            Finding("SIDECAR_MISSING", "ERROR", rel, f"sidecar 解析失败：{exc}")
        )
        return
    if not isinstance(meta, dict):
        report.findings.append(
            Finding("SIDECAR_MISSING", "ERROR", rel, "sidecar 顶层必须是映射")
        )
        return

    missing_fields = [f for f in required if f not in meta]
    if missing_fields:
        report.findings.append(
            Finding(
                "SIDECAR_MISSING",
                "ERROR",
                rel,
                f"sidecar 缺字段：{missing_fields}",
                f"必填字段：{required}",
            )
        )

    derived_from = _normalize_list(meta.get("derived_from"))
    input_sha = _normalize_list(meta.get("input_sha256"))
    if not derived_from:
        report.findings.append(
            Finding("DERIVED_INPUT_EMPTY", "ERROR", rel, "derived_from 为空")
        )

    method = str(meta.get("method", ""))
    if methods and method not in methods:
        report.findings.append(
            Finding(
                "SIDECAR_MISSING",
                "ERROR",
                rel,
                f"method={method!r} 不在 {methods} 内",
            )
        )

    tool = str(meta.get("tool", "") or "").strip()
    if not tool:
        report.findings.append(
            Finding("SIDECAR_MISSING", "ERROR", rel, "tool 不能为空（manual 也要写 manual）")
        )

    reviewer = str(meta.get("reviewed_by", "") or "").strip()
    if is_forbidden_name(reviewer, forbidden):
        report.findings.append(
            Finding(
                "DERIVED_NOT_REVIEWED",
                "ERROR",
                rel,
                f"reviewed_by={reviewer!r} 不是实名",
                f"称谓黑名单：{forbidden}；必须由真人签自己的名字",
            )
        )

    if derived_from and len(input_sha) != len(derived_from):
        report.findings.append(
            Finding(
                "SIDECAR_MISSING",
                "ERROR",
                rel,
                "derived_from 与 input_sha256 数量不一致",
            )
        )

    if manifest:
        for idx, source in enumerate(derived_from):
            source_name = Path(str(source)).name
            if source_name not in manifest:
                report.findings.append(
                    Finding(
                        "DERIVED_INPUT_NOT_IN_LIBRARY",
                        "ERROR",
                        rel,
                        f"引用的输入不在库：{source}",
                        "先把输入入库，再入衍生件（跨人顺序：所有人的 data 收完再收 derived）",
                    )
                )
                continue
            if idx < len(input_sha) and str(input_sha[idx]) != manifest[source_name]:
                report.findings.append(
                    Finding(
                        "DERIVED_INPUT_NOT_IN_LIBRARY",
                        "ERROR",
                        rel,
                        f"引用的输入版本变了：{source}",
                        "从 manifest 抄 input_sha256，不要自己另算",
                    )
                )


# ---------------------------------------------------------------------------
# outputs
# ---------------------------------------------------------------------------
def _write_outputs(
    report: CheckReport,
    out_dir: Path,
    prior: Mapping[Tuple[str, str], Mapping[str, str]],
) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    lines: List[str] = []
    lines.append("AI4S self-check report")
    lines.append(f"generated_at: {report.generated_at}")
    lines.append(f"root: {report.root}")
    lines.append(f"registry_snapshot: {report.snapshot_id}")
    lines.append(f"files: {report.files}  bytes: {report.bytes}")
    lines.append(f"errors: {len(report.errors)}  warnings: {len(report.warnings)}")
    lines.append("")
    if report.errors:
        lines.append("== ERRORS ==")
        for f in report.errors:
            lines.append(f"[{f.code}] {f.subject}")
            lines.append(f"    reason: {f.message}")
            if f.hint:
                lines.append(f"    do: {f.hint}")
        lines.append("")
    if report.warnings:
        lines.append("== WARNINGS (answer, do not 'fix') ==")
        for f in report.warnings:
            lines.append(f"[{f.code}] {f.subject}")
            lines.append(f"    question: {f.message}")
            if f.hint:
                lines.append(f"    ask: {f.hint}")
        lines.append("")
    lines.append(f"conclusion: {'PASS' if report.ok else 'FAILED'}")
    (out_dir / "_selfcheck_report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    with (out_dir / "_delivery_list.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["filename", "bytes"])
        for path in sorted(_iter_files(report.root)):
            writer.writerow([path.name, path.stat().st_size])

    with (out_dir / "_pending.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "category",
                "subject",
                "who",
                "question_do",
                "answer",
                "previous_answer",
            ]
        )
        for f in report.warnings:
            key = (f.code, f.subject)
            old = prior.get(key, {})
            answer = old.get("answer", "")
            previous = old.get("answer", "") if old else ""
            writer.writerow(
                [f.code, f.subject, f.who, f.hint or f.message, answer, previous]
            )

    if report.ok:
        total = report.files
        answered = f"{report.warnings_answered}/{report.warnings_total}"
        credential = [
            "AI4S DELIVERY CREDENTIAL",
            "=========================",
            f"generated_at      : {report.generated_at}",
            f"delivery_root     : {report.root}",
            f"registry_snapshot : {report.snapshot_id}",
            f"files             : {total}",
            f"bytes             : {report.bytes}",
            f"errors            : 0",
            f"warnings          : {report.warnings_total}",
            f"warnings_answered : {answered}",
            f"delivery_list     : _delivery_list.csv",
            f"conclusion        : PASS",
            "",
            "This credential only proves the batch named above passed the checks",
            "implemented in this tool at this moment. It is not a statement that",
            "the science is correct.",
        ]
        (out_dir / "_credential.txt").write_text(
            "\n".join(credential) + "\n", encoding="utf-8"
        )
    else:
        stale = out_dir / "_credential.txt"
        if stale.exists():
            stale.unlink()


def format_summary(report: CheckReport, limit: int = 40) -> str:
    buf = io.StringIO()
    buf.write(
        f"{report.files} files, {len(report.errors)} ERROR, "
        f"{len(report.warnings)} WARN, "
        f"answered {report.warnings_answered}/{report.warnings_total}\n"
    )
    for f in report.errors[:limit]:
        buf.write(f"  E {f.code:<30} {f.subject}\n")
    if len(report.errors) > limit:
        buf.write(f"  … {len(report.errors) - limit} more errors\n")
    for f in report.warnings[:limit]:
        buf.write(f"  W {f.code:<30} {f.subject}\n")
    if len(report.warnings) > limit:
        buf.write(f"  … {len(report.warnings) - limit} more warnings\n")
    buf.write(f"conclusion: {'PASS' if report.ok else 'FAILED'}\n")
    return buf.getvalue()
