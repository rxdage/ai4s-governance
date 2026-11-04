"""A read-only lab data health check.

This is the lead magnet: point it at a folder, get a one-page report that says
how many filenames a machine can parse, what breaks most often, and what to fix
first. It never modifies the scanned folder.

The report is deliberately honest: it measures *shape*, not science.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from . import naming
from .registry import Registry

CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")
VERSION_RE = re.compile(r"(?i)(final|copy|副本|最终|最新|new|old|backup|bak|v[0-9]+)")
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", ".pytest_cache"}


@dataclass
class AuditResult:
    label: str
    generated_at: str
    files: int = 0
    bytes: int = 0
    sidecars: int = 0
    syntax_ok: int = 0
    registry_checked: bool = False
    registry_ok: int = 0
    error_counts: Counter = field(default_factory=Counter)
    examples: Dict[str, List[str]] = field(default_factory=dict)
    registry_errors: Counter = field(default_factory=Counter)
    legacy: Counter = field(default_factory=Counter)
    duplicates: List[Dict[str, Any]] = field(default_factory=list)
    extensions: Counter = field(default_factory=Counter)
    top_identities: List[Tuple[str, int]] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    root: str = ""

    @property
    def syntax_ok_pct(self) -> float:
        return round(100.0 * self.syntax_ok / self.files, 1) if self.files else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "root": self.root,
            "generated_at": self.generated_at,
            "files": self.files,
            "bytes": self.bytes,
            "sidecars": self.sidecars,
            "syntax_ok": self.syntax_ok,
            "syntax_ok_pct": self.syntax_ok_pct,
            "registry_checked": self.registry_checked,
            "registry_ok": self.registry_ok,
            "error_counts": dict(self.error_counts.most_common()),
            "registry_errors": dict(self.registry_errors.most_common()),
            "legacy": dict(self.legacy.most_common()),
            "duplicates": self.duplicates,
            "extensions": dict(self.extensions.most_common(20)),
            "top_identities": [
                {"identity": identity, "files": count}
                for identity, count in self.top_identities
            ],
            "recommendations": self.recommendations,
        }


def _walk(root: Path) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d
            for d in dirnames
            if not d.startswith(("_", "~$", ".")) and d not in SKIP_DIRS
        ]
        for filename in filenames:
            if filename.startswith(("_", "~$", ".")):
                continue
            yield Path(dirpath) / filename


def _add_example(result: AuditResult, code: str, name: str, limit: int = 3) -> None:
    bucket = result.examples.setdefault(code, [])
    if len(bucket) < limit:
        bucket.append(name)


def _legacy(name: str) -> List[str]:
    stem = name.split(".", 1)[0]
    found = []
    if " " in name:
        found.append("space")
    if CHINESE_RE.search(name):
        found.append("chinese")
    if VERSION_RE.search(stem):
        found.append("version")
    if "." not in name:
        found.append("no_extension")
    if "-" in name:
        found.append("hyphen")
    if stem != stem.upper():
        found.append("lowercase")
    return found


def _recommend(result: AuditResult) -> List[str]:
    rec: List[str] = []
    if result.files == 0:
        return ["No data files found. Check the path and the skip rules (names starting with `_` are ignored)."]
    if result.legacy.get("space") or result.legacy.get("chinese"):
        rec.append(
            "Remove spaces and Chinese characters from filenames first; they break shell, URL and agent parsing."
        )
    if result.error_counts.get("ZONE_COUNT") or result.error_counts.get("ZONE1_SYNTAX"):
        rec.append(
            "Adopt one four-zone shape (`R####_W####_D####__TYPE__COND__T##########_RUN####.ext`) for the next batch."
        )
    if result.error_counts.get("EXT_MISSING"):
        rec.append("Give every file an extension; a name without one is not machine-identifiable.")
    if result.error_counts.get("TYPE_SYNTAX") or result.error_counts.get("CODE_SYNTAX"):
        rec.append("Separate type codes (letters) from condition codes (`CLASS + number`).")
    if result.duplicates:
        rec.append(
            "Resolve duplicate full names before ingesting; a library cannot hold two different files with one name."
        )
    if result.registry_checked and result.registry_ok < result.files:
        rec.append(
            "Some names use codes the registry does not approve (missing or unsigned). Check the registry issues before renaming."
        )
    if not rec and result.syntax_ok_pct == 100.0:
        rec.append(
            "All names are parseable. Next: run `ai4s check` on one batch to verify content and registered codes."
        )
    if not rec and result.syntax_ok_pct >= 90:
        rec.append(
            "You are close. Pick one batch of 10-50 files, dry-run a rename, and run `ai4s check` on it."
        )
    if not rec:
        rec.append(
            "Start with the most common error above on one small batch; do not attempt a full migration first."
        )
    return rec[:3]


def _read_names_file(path: Path) -> List[Tuple[str, Optional[Path]]]:
    entries: List[Tuple[str, Optional[Path]]] = []
    for line in Path(path).read_text(encoding="utf-8", errors="ignore").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        rel = raw.replace("\\", "/").lstrip("./")
        if rel:
            entries.append((rel, None))
    return entries


def audit(
    root: Optional[Path] = None,
    registry: Optional[Registry] = None,
    schema: Optional[Mapping[str, Any]] = None,
    label: Optional[str] = None,
    top: int = 10,
    names_file: Optional[Path] = None,
) -> AuditResult:
    if names_file is None and root is None:
        raise ValueError("pass a directory or a names file")
    schema = schema or (registry.schema if registry else naming.load_schema())
    result = AuditResult(
        label=label or "lab-data",
        generated_at=datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S%z"),
        root=str(Path(names_file or root).resolve()),
        registry_checked=registry is not None,
    )

    if names_file is not None:
        entries: List[Tuple[str, Optional[Path]]] = _read_names_file(Path(names_file))
    else:
        root = Path(root)  # type: ignore[arg-type]
        if not root.is_dir():
            raise FileNotFoundError(f"not a directory: {root}")
        entries = [
            (str(path.relative_to(root)).replace("\\", "/"), path)
            for path in sorted(_walk(root))
        ]

    names: Counter = Counter()
    paths: Dict[str, List[str]] = {}
    identities: Counter = Counter()

    for rel, path in entries:
        name = rel.rsplit("/", 1)[-1]
        if name.startswith(("_", "~$", ".")):
            continue
        if name.endswith(".meta.yaml"):
            result.sidecars += 1
            continue
        result.files += 1
        if path is not None:
            try:
                result.bytes += path.stat().st_size
            except OSError:
                pass
        names[name] += 1
        paths.setdefault(name, []).append(rel)
        if "." in name:
            result.extensions["." + name.rsplit(".", 1)[1].lower()] += 1
        else:
            result.extensions["(none)"] += 1
        for token in _legacy(name):
            result.legacy[token] += 1

        parsed = naming.parse(name, schema=schema, check_registry=False)
        if parsed.ok:
            result.syntax_ok += 1
            if parsed.batch is not None:
                identities[f"R{parsed.batch:04d}_{parsed.sample}_{parsed.unit}"] += 1
        else:
            for issue in parsed.errors:
                result.error_counts[issue.code] += 1
                _add_example(result, issue.code, name)

        if registry is not None:
            checked = naming.parse(name, registry=registry.as_mapping(), schema=schema)
            if checked.ok:
                result.registry_ok += 1
            else:
                for issue in checked.errors:
                    if issue.code not in {
                        "ZONE_COUNT",
                        "ZONE1_SYNTAX",
                        "ZONE1_ALL_MIX",
                        "ZONE1_LIBRARY_MIX",
                        "ZONE1_NUMBERING",
                        "TYPE_SYNTAX",
                        "CODE_SYNTAX",
                        "COND_DUPLICATE_CLASS",
                        "COND_NA_MIXED",
                        "TIME_INVALID",
                        "ZONE4_SYNTAX",
                        "EXT_MISSING",
                        "CHARSET_INVALID",
                        "BODY_NOT_UPPERCASE",
                    }:
                        result.registry_errors[issue.code] += 1

    result.duplicates = [
        {"name": name, "count": count, "paths": paths[name][:5]}
        for name, count in names.most_common()
        if count > 1
    ][:top]
    result.top_identities = identities.most_common(top)
    result.recommendations = _recommend(result)
    return result


def render_markdown(result: AuditResult, top: int = 10) -> str:
    lines: List[str] = []
    lines.append("# Lab data health check")
    lines.append("")
    lines.append(f"- **Label:** {result.label}")
    lines.append(f"- **Generated:** {result.generated_at}")
    lines.append(f"- **Files:** {result.files}  |  **Sidecars:** {result.sidecars}")
    lines.append("- **No files were modified.** This report only reads names and sizes.")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---:|")
    lines.append(f"| Files | {result.files} |")
    lines.append(f"| Machine-parseable names | {result.syntax_ok} / {result.files} ({result.syntax_ok_pct}%) |")
    if result.registry_checked:
        lines.append(f"| Names valid against the registry | {result.registry_ok} / {result.files} |")
    lines.append(f"| Duplicate full names | {len(result.duplicates)} |")
    lines.append(f"| Sidecars | {result.sidecars} |")
    lines.append("")
    if result.error_counts:
        lines.append("## Top syntax issues")
        lines.append("")
        lines.append("| Error | Count | Example |")
        lines.append("|---|---:|---|")
        for code, count in result.error_counts.most_common(top):
            example = (result.examples.get(code) or [""])[0]
            lines.append(f"| `{code}` | {count} | `{example}` |")
        lines.append("")
    if result.registry_errors:
        lines.append("## Registry issues")
        lines.append("")
        lines.append("| Error | Count |")
        lines.append("|---|---:|")
        for code, count in result.registry_errors.most_common(top):
            lines.append(f"| `{code}` | {count} |")
        lines.append("")
    if result.legacy:
        lines.append("## Legacy patterns")
        lines.append("")
        lines.append("| Pattern | Files |")
        lines.append("|---|---:|")
        for token, count in result.legacy.most_common():
            lines.append(f"| {token} | {count} |")
        lines.append("")
    if result.duplicates:
        lines.append("## Duplicate full names")
        lines.append("")
        for row in result.duplicates[:top]:
            lines.append(f"- `{row['name']}` x {row['count']}  ({', '.join(row['paths'])})")
        lines.append("")
    if result.top_identities:
        lines.append("## Identities with the most files")
        lines.append("")
        lines.append("| Identity | Files |")
        lines.append("|---|---:|")
        for identity, count in result.top_identities[:top]:
            lines.append(f"| `{identity}` | {count} |")
        lines.append("")
    lines.append("## What to fix first")
    lines.append("")
    for idx, rec in enumerate(result.recommendations, 1):
        lines.append(f"{idx}. {rec}")
    lines.append("")
    lines.append("## What this report cannot tell you")
    lines.append("")
    lines.append("- Whether the science is right.")
    lines.append("- Whether a code means the same thing as it did last month.")
    lines.append("- Whether a file is measured or computed (that needs the registry's `derived` flag).")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("Generated by `ai4s audit` (ai4s-governance). No files were changed.")
    return "\n".join(lines) + "\n"


def write_report(result: AuditResult, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(result), encoding="utf-8")
    return path


def format_summary(result: AuditResult) -> str:
    return (
        f"{result.files} files, {result.syntax_ok} parseable "
        f"({result.syntax_ok_pct}%), {len(result.duplicates)} duplicate name(s), "
        f"{result.sidecars} sidecar(s)"
    )
