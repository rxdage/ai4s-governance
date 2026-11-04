"""Patrol: one screen that answers "who is blocked on what".

This is the read-only half of the operating cadence. It never changes state and
never sends messages; it only produces a JSON snapshot plus a human summary.
The steward decides what to release, sign or waive.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

import yaml

from . import ingest, naming, selfcheck
from .registry import Registry, load_registry


def load_lab(path: Path) -> Dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    if "people" not in cfg:
        raise ValueError("lab config needs a `people:` list")
    return cfg


def resolve(base: Path, value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else (Path(base) / p).resolve()


@dataclass
class PersonStatus:
    id: str
    name: str
    role: str
    workspace: str
    files: int = 0
    errors: int = 0
    warnings: int = 0
    unanswered: int = 0
    has_credential: bool = False
    credential_age_days: Optional[int] = None
    issues: List[Dict[str, str]] = field(default_factory=list)
    proposals_new: int = 0
    proposals_linger: int = 0

    @property
    def blocked(self) -> bool:
        return any(i["level"] == "BLOCK" for i in self.issues)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "workspace": self.workspace,
            "files": self.files,
            "errors": self.errors,
            "warnings": self.warnings,
            "unanswered": self.unanswered,
            "has_credential": self.has_credential,
            "credential_age_days": self.credential_age_days,
            "proposals_new": self.proposals_new,
            "proposals_linger": self.proposals_linger,
            "blocked": self.blocked,
            "issues": self.issues,
        }


def _proposal_names(workspace: Path) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {"types": [], "classes": [], "codes": []}
    reg_dir = workspace / "REGISTRY"
    if not reg_dir.is_dir():
        return out
    for path in sorted(reg_dir.glob("*.yaml")):
        try:
            with path.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        for kind in out:
            table = data.get(kind) or {}
            if isinstance(table, dict):
                out[kind].extend(str(k) for k in table)
    return out


def _check_proposals(
    status: PersonStatus,
    workspace: Path,
    registry: Registry,
) -> None:
    kind_of = {"types": "type", "classes": "class", "codes": "code"}
    proposals = _proposal_names(workspace)
    signed = 0
    for kind, names in proposals.items():
        table = registry.table(kind_of[kind])
        for name in names:
            entry = table.get(name)
            if entry is None:
                status.proposals_new += 1
                continue
            if entry.get("_signature_state") == "valid":
                status.proposals_linger += 1
                signed += 1
    if signed:
        status.issues.append(
            {
                "code": "REG_LINGER",
                "level": "WARN",
                "text": f"{signed} 条提案已在总表签字，请清出 REGISTRY/（字典夹是纯增量）",
            }
        )


def run(config_path: Path) -> Dict[str, Any]:
    cfg_path = Path(config_path).resolve()
    base = cfg_path.parent
    cfg = load_lab(cfg_path)
    registry = load_registry(resolve(base, cfg.get("paths", {}).get("registry", "registry")))
    library = resolve(base, cfg.get("paths", {}).get("library", "library"))
    manifest = ingest.manifest_sha_map(library)
    max_age = int(cfg.get("policy", {}).get("credential_max_age_days", 7))

    out: Dict[str, Any] = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "lab": cfg.get("lab", {}).get("name", cfg_path.stem),
        "library": str(library),
        "registry": registry.summary(),
        "persons": [],
        "summary": {},
    }

    for person in cfg.get("people", []):
        ws = resolve(base, str(person.get("workspace", "")))
        st = PersonStatus(
            id=str(person.get("id", "")),
            name=str(person.get("name", person.get("id", ""))),
            role=str(person.get("role", "owner")),
            workspace=str(ws),
        )
        data_root = ws / "SR_DATA"
        if not data_root.is_dir():
            st.issues.append(
                {"code": "NO_SR_DATA", "level": "INFO", "text": "SR_DATA/ 不存在"}
            )
            out["persons"].append(st.to_dict())
            continue

        report = selfcheck.check_delivery(
            data_root,
            registry,
            manifest=manifest,
            write=False,
        )
        st.files = report.files
        st.errors = len(report.errors)
        st.warnings = len(report.warnings)
        st.unanswered = report.warnings_total - report.warnings_answered

        cred = data_root / "_credential.txt"
        if cred.is_file() and report.files:
            st.has_credential = True
            age = (datetime.now() - datetime.fromtimestamp(cred.stat().st_mtime)).days
            st.credential_age_days = age
        if report.files and not st.has_credential:
            st.issues.append(
                {
                    "code": "NO_CRED",
                    "level": "BLOCK",
                    "text": f"{report.files} 个文件没有 PASS 凭据",
                }
            )
        if st.credential_age_days is not None and st.credential_age_days > max_age:
            st.issues.append(
                {
                    "code": "STALE_CRED",
                    "level": "WARN",
                    "text": f"凭据已 {st.credential_age_days} 天未更新（阈值 {max_age}）",
                }
            )
        if st.errors:
            codes = sorted({f.code for f in report.errors})
            st.issues.append(
                {
                    "code": "ERRORS",
                    "level": "BLOCK",
                    "text": f"{st.errors} 个 ERROR：" + ", ".join(codes[:6]),
                }
            )
        if st.unanswered:
            st.issues.append(
                {
                    "code": "PEND",
                    "level": "WARN",
                    "text": f"{st.unanswered} 条 WARN 还没答复（要本人答，不是改）",
                }
            )

        _check_proposals(st, ws, registry)
        out["persons"].append(st.to_dict())

    blocked = [p["id"] for p in out["persons"] if p["blocked"]]
    out["summary"] = {
        "people": len(out["persons"]),
        "blocked": blocked,
        "files": sum(p["files"] for p in out["persons"]),
        "errors": sum(p["errors"] for p in out["persons"]),
        "unanswered": sum(p["unanswered"] for p in out["persons"]),
    }
    return out


def format_report(data: Mapping[str, Any]) -> str:
    lines = [
        f"patrol @ {data['generated_at']}  lab={data['lab']}",
        f"people={data['summary']['people']} files={data['summary']['files']} "
        f"errors={data['summary']['errors']} unanswered={data['summary']['unanswered']}",
        "",
    ]
    for p in data["persons"]:
        flag = "BLOCKED" if p["blocked"] else "ok"
        lines.append(
            f"[{flag:7}] {p['name']:<12} files={p['files']:<4} "
            f"E={p['errors']:<3} W={p['warnings']:<3} unanswered={p['unanswered']:<3} "
            f"cred={'yes' if p['has_credential'] else 'no'}"
        )
        for issue in p["issues"]:
            lines.append(f"          {issue['level']:<5} {issue['code']:<10} {issue['text']}")
    return "\n".join(lines)
