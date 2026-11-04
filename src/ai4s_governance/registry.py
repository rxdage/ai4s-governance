"""Registry loading, validation and hash-bound signatures.

Why signatures are separate from entries
----------------------------------------
The production system this playbook comes from stored ``status: APPROVED`` and
``approved_by`` *inside* each entry. That works until someone edits an approved
entry, or an AI fills in an approver name: the label says APPROVED while the
content has changed. The public edition moves approval into an append-only
``signatures.yaml`` that binds each signature to a sha256 of the canonical
entry. Edit one character after signing and the signature stops verifying.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

import yaml

from . import naming

KINDS = {"type": "types", "class": "classes", "code": "codes"}
TABLE_OF_KIND = KINDS


def _read_yaml(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"expected a mapping at the top level: {path}")
    return data


def _write_yaml(path: Path, data: Mapping[str, Any], header: str = "") -> None:
    text = yaml.safe_dump(
        dict(data), allow_unicode=True, sort_keys=False, default_flow_style=False
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        if header:
            fh.write(header)
            if not header.endswith("\n"):
                fh.write("\n")
        fh.write(text)


def canonical_entry(entry: Mapping[str, Any]) -> str:
    clean = {k: v for k, v in entry.items() if not str(k).startswith("_")}
    return json.dumps(
        clean, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )


def is_forbidden_name(name: str, forbidden: Iterable[str]) -> bool:
    """A signature/review must be a real person's name, not a role label."""
    value = str(name or "").strip().casefold()
    if not value:
        return True
    return value in {str(item).strip().casefold() for item in forbidden}


def entry_sha256(entry: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_entry(entry).encode("utf-8")).hexdigest()


@dataclass
class CheckResult:
    errors: List[naming.Issue] = field(default_factory=list)
    warnings: List[naming.Issue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": [i.to_dict() for i in self.errors],
            "warnings": [i.to_dict() for i in self.warnings],
        }


class Registry:
    def __init__(self, path: Path, schema: Optional[Mapping[str, Any]] = None):
        self.dir = Path(path)
        self.schema = schema or naming.load_schema()
        self.types: Dict[str, Dict[str, Any]] = {}
        self.classes: Dict[str, Dict[str, Any]] = {}
        self.codes: Dict[str, Dict[str, Any]] = {}
        self.classification: Dict[str, Any] = {}
        self.signatures: List[Dict[str, Any]] = []
        self.load()

    # -- io ---------------------------------------------------------------
    def load(self) -> "Registry":
        files = self.schema.get("registry", {}).get("files", {})
        self.types = _read_yaml(self.dir / files.get("types", "types.yaml")).get(
            "types", {}
        ) or {}
        self.classes = _read_yaml(self.dir / files.get("classes", "classes.yaml")).get(
            "classes", {}
        ) or {}
        self.codes = _read_yaml(self.dir / files.get("codes", "codes.yaml")).get(
            "codes", {}
        ) or {}
        cls = _read_yaml(self.dir / files.get("classification", "classification.yaml"))
        self.classification = cls.get("classification", cls) or {}
        sig = _read_yaml(self.dir / files.get("signatures", "signatures.yaml"))
        self.signatures = sig.get("signatures", []) or []
        self.resolve()
        return self

    def save_signatures(self) -> None:
        files = self.schema.get("registry", {}).get("files", {})
        header = (
            "# Append-only signature ledger. Each record binds a sha256 of the\n"
            "# canonical entry at the moment it was signed. Do not hand-edit;\n"
            "# use `ai4s registry sign` / `ai4s registry revoke`.\n"
        )
        _write_yaml(
            self.dir / files.get("signatures", "signatures.yaml"),
            {"signatures": self.signatures},
            header,
        )

    # -- resolution -------------------------------------------------------
    def latest_signature(self, kind: str, name: str) -> Optional[Dict[str, Any]]:
        found = None
        for rec in self.signatures:
            if rec.get("kind") == kind and rec.get("name") == name:
                found = rec
        return found

    def resolve(self) -> None:
        """Compute ``_signature_state`` for every entry (in memory only)."""
        for table in (self.types, self.classes, self.codes):
            for entry in table.values():
                if isinstance(entry, dict):
                    entry["_signature_state"] = "missing"

        for kind, table in (
            ("type", self.types),
            ("class", self.classes),
            ("code", self.codes),
        ):
            for name, entry in table.items():
                if not isinstance(entry, dict):
                    continue
                entry["_effective_status"] = "PROPOSED"
                if entry.get("status") == "DEPRECATED":
                    entry["_signature_state"] = "n/a"
                    entry["_effective_status"] = "DEPRECATED"
                    continue
                rec = self.latest_signature(kind, name)
                if rec is None:
                    continue
                if rec.get("revoked"):
                    entry["_signature_state"] = "revoked"
                elif rec.get("content_sha256") == entry_sha256(entry):
                    entry["_signature_state"] = "valid"
                    entry["_effective_status"] = "APPROVED"
                else:
                    entry["_signature_state"] = "stale"
                    entry["_effective_status"] = "SIGNATURE_STALE"

    # -- access -----------------------------------------------------------
    def table(self, kind: str) -> Dict[str, Dict[str, Any]]:
        return {"type": self.types, "class": self.classes, "code": self.codes}[kind]

    def as_mapping(self) -> Dict[str, Any]:
        return {
            "types": self.types,
            "classes": self.classes,
            "codes": self.codes,
            "classification": self.classification,
        }

    def summary(self) -> Dict[str, Dict[str, int]]:
        out: Dict[str, Dict[str, int]] = {}
        for kind, table in (
            ("types", self.types),
            ("classes", self.classes),
            ("codes", self.codes),
        ):
            counts = {"total": len(table), "approved": 0, "proposed": 0, "deprecated": 0}
            for entry in table.values():
                status = naming.effective_status(entry) if isinstance(entry, dict) else ""
                if status == "DEPRECATED":
                    counts["deprecated"] += 1
                elif status == "APPROVED":
                    counts["approved"] += 1
                else:
                    counts["proposed"] += 1
            out[kind] = counts
        return out

    # -- validation -------------------------------------------------------
    def check(self) -> CheckResult:
        res = CheckResult()
        sch = self.schema
        reg = sch.get("registry", {})
        forbidden = [str(x) for x in reg.get("forbidden_approvers", [])]
        statuses = [str(x) for x in reg.get("statuses", ["PROPOSED", "DEPRECATED", "REJECTED"])]
        reserved = set(str(x) for x in sch.get("semantics", {}).get("reserved_words", []))

        type_re = re.compile("^" + sch["zones"]["zone2"]["pattern"] + "$")
        class_re = re.compile(r"^[A-Z]{2,12}$")

        for name, entry in self.types.items():
            self._check_common(res, "type", name, entry, statuses)
            if not type_re.match(name):
                res.errors.append(
                    naming.Issue("TYPE_SYNTAX", "ERROR", f"类型码 {name} 不是 2–15 个纯大写字母")
                )
            if name in reserved:
                res.errors.append(
                    naming.Issue("TYPE_SYNTAX", "ERROR", f"类型码 {name} 是保留字")
                )
            if not isinstance(entry.get("derived"), bool):
                res.errors.append(
                    naming.Issue(
                        "STATUS_INVALID",
                        "ERROR",
                        f"类型码 {name} 的 derived 必须是布尔值 true/false（不能加引号）",
                    )
                )
            if not entry.get("description"):
                res.errors.append(
                    naming.Issue("STATUS_INVALID", "ERROR", f"类型码 {name} 缺 description")
                )

        for name, entry in self.classes.items():
            self._check_common(res, "class", name, entry, statuses)
            if not class_re.match(name):
                res.errors.append(
                    naming.Issue("CODE_SYNTAX", "ERROR", f"class 名 {name} 不合法")
                )
            for required in ("owner", "scope", "description"):
                if not entry.get(required):
                    res.errors.append(
                        naming.Issue(
                            "STATUS_INVALID", "ERROR", f"class {name} 缺 {required}"
                        )
                    )

        seen_instances: Dict[str, str] = {}
        for name, entry in self.codes.items():
            self._check_common(res, "code", name, entry, statuses)
            cls = str(entry.get("class", ""))
            if cls not in self.classes:
                res.errors.append(
                    naming.Issue(
                        "CLASS_MISSING", "ERROR", f"条件码 {name} 指向不存在的 class {cls!r}"
                    )
                )
            if not name.startswith(cls):
                res.errors.append(
                    naming.Issue(
                        "CODE_SYNTAX", "ERROR", f"条件码 {name} 与 class {cls} 前缀不符"
                    )
                )
            m = re.match(r"^([A-Z]{2,12})(0|[1-9][0-9]{0,3})$", name)
            if not m:
                res.errors.append(
                    naming.Issue(
                        "CODE_SYNTAX",
                        "ERROR",
                        f"条件码 {name} 必须是 class+数字，且数字不补零",
                    )
                )
            instance = str(entry.get("instance", "")).strip()
            if not instance:
                res.errors.append(
                    naming.Issue(
                        "STATUS_INVALID", "ERROR", f"条件码 {name} 的 instance 不能为空"
                    )
                )
            elif instance in seen_instances and seen_instances[instance] != name:
                res.errors.append(
                    naming.Issue(
                        "DUPLICATE_INSTANCE",
                        "ERROR",
                        f"{name} 与 {seen_instances[instance]} 的 instance 完全相同",
                    )
                )
            else:
                seen_instances[instance] = name
            if entry.get("status") == "DEPRECATED" and not (
                entry.get("superseded_by") or entry.get("deprecated_reason")
            ):
                res.errors.append(
                    naming.Issue(
                        "STATUS_INVALID",
                        "ERROR",
                        f"作废的 {name} 必须写 superseded_by 或 deprecated_reason",
                    )
                )

        # signatures
        latest: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for rec in self.signatures:
            kind, name = rec.get("kind"), rec.get("name")
            if kind not in KINDS or not name:
                res.errors.append(
                    naming.Issue(
                        "SIGNATURE_UNKNOWN",
                        "ERROR",
                        f"签名记录缺少 kind/name 或 kind 非法：{rec!r}",
                    )
                )
                continue
            latest[(str(kind), str(name))] = rec

        for (kind, name), rec in latest.items():
            entry = self.table(kind).get(name)
            if entry is None:
                res.errors.append(
                    naming.Issue(
                        "SIGNATURE_UNKNOWN",
                        "ERROR",
                        f"签名指向不存在的 {kind}: {name}",
                    )
                )
                continue
            if rec.get("revoked"):
                continue
            who = str(rec.get("approved_by", ""))
            if is_forbidden_name(who, forbidden):
                res.errors.append(
                    naming.Issue(
                        "STATUS_INVALID",
                        "ERROR",
                        f"{kind} {name} 的签字人 {who!r} 不是实名",
                    )
                )
            if rec.get("content_sha256") != entry_sha256(entry):
                res.errors.append(
                    naming.Issue(
                        "SIGNATURE_STALE",
                        "ERROR",
                        f"{kind} {name} 在签字后被改动，必须重签",
                    )
                )

        for kind, table in (
            ("type", self.types),
            ("class", self.classes),
            ("code", self.codes),
        ):
            for name, entry in table.items():
                if not isinstance(entry, dict):
                    continue
                if entry.get("status") == "APPROVED":
                    res.warnings.append(
                        naming.Issue(
                            "STATUS_INVALID",
                            "WARN",
                            f"{kind} {name} 写了 status: APPROVED；公开版以 signatures.yaml 为准，这个标签会被忽略",
                        )
                    )
                if naming.effective_status(entry) == "PROPOSED":
                    res.warnings.append(
                        naming.Issue(
                            "STATUS_INVALID",
                            "WARN",
                            f"{kind} {name} 尚未签字（PROPOSED），不能出现在归档文件名里",
                        )
                    )

        # classification
        levels = [str(x) for x in reg.get("classification_levels", [])]
        cls_types = self.classification.get("types", {}) or {}
        for tname, level in cls_types.items():
            if tname not in self.types:
                res.errors.append(
                    naming.Issue(
                        "STATUS_INVALID",
                        "ERROR",
                        f"classification 指向未注册的类型码 {tname}",
                    )
                )
            if levels and str(level) not in levels:
                res.errors.append(
                    naming.Issue(
                        "STATUS_INVALID",
                        "ERROR",
                        f"类型码 {tname} 的密级 {level!r} 不在 {levels} 内",
                    )
                )
        return res

    def _check_common(
        self,
        res: CheckResult,
        kind: str,
        name: str,
        entry: Any,
        statuses: Iterable[str],
    ) -> None:
        if not isinstance(entry, dict):
            res.errors.append(
                naming.Issue("STATUS_INVALID", "ERROR", f"{kind} {name} 不是映射")
            )
            return
        status = entry.get("status", "PROPOSED")
        if status not in list(statuses) + ["APPROVED"]:
            res.errors.append(
                naming.Issue(
                    "STATUS_INVALID", "ERROR", f"{kind} {name} 的 status {status!r} 非法"
                )
            )
        for required in ("proposer", "proposed_at"):
            if not entry.get(required):
                res.errors.append(
                    naming.Issue(
                        "STATUS_INVALID", "ERROR", f"{kind} {name} 缺 {required}"
                    )
                )

    # -- signing ----------------------------------------------------------
    def sign(
        self,
        kind: str,
        names: Iterable[str],
        who: str,
        on: str,
        note: str = "",
        apply: bool = False,
    ) -> List[str]:
        """Return human-readable actions; only writes when ``apply`` is true."""
        if kind not in KINDS:
            raise ValueError(f"kind must be one of {sorted(KINDS)}")
        who = who.strip()
        forbidden = [
            str(x) for x in self.schema.get("registry", {}).get("forbidden_approvers", [])
        ]
        if is_forbidden_name(who, forbidden):
            raise ValueError(f"签字人 {who!r} 是称谓，不是实名；黑名单：{forbidden}")
        try:
            datetime.strptime(on, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"日期必须是 YYYY-MM-DD：{on!r}")

        actions: List[str] = []
        for name in names:
            entry = self.table(kind).get(name)
            if entry is None:
                raise KeyError(f"{kind} 不存在：{name}")
            if entry.get("status") == "DEPRECATED":
                raise ValueError(f"{kind} {name} 已作废，不能签字")
            digest = entry_sha256(entry)
            actions.append(f"sign {kind}:{name} sha256={digest[:12]}… by {who} on {on}")
            if apply:
                self.signatures.append(
                    {
                        "kind": kind,
                        "name": name,
                        "content_sha256": digest,
                        "approved_by": who,
                        "approved_at": on,
                        "note": note,
                    }
                )
        if apply and actions:
            self.save_signatures()
            self.load()
        return actions

    def revoke(
        self, kind: str, name: str, who: str, on: str, reason: str, apply: bool = False
    ) -> str:
        if kind not in KINDS:
            raise ValueError(f"kind must be one of {sorted(KINDS)}")
        action = f"revoke {kind}:{name} by {who} on {on}: {reason}"
        if apply:
            self.signatures.append(
                {
                    "kind": kind,
                    "name": name,
                    "revoked": True,
                    "revoked_by": who,
                    "revoked_at": on,
                    "reason": reason,
                }
            )
            self.save_signatures()
            self.load()
        return action


def load_registry(path: Path, schema: Optional[Mapping[str, Any]] = None) -> Registry:
    return Registry(Path(path), schema=schema)


def scaffold(path: Path, force: bool = False) -> List[Path]:
    """Create an empty, valid registry skeleton."""
    path = Path(path)
    existing = [p for p in path.glob("*.yaml")] if path.is_dir() else []
    if existing and not force:
        raise FileExistsError(f"registry already has yaml files: {path}")
    now = date.today().isoformat()
    files = {
        "types.yaml": {
            "types": {
                "MEAS": {
                    "name_cn": "测量数据",
                    "description": "仪器直接产出的一次采集（示例码，可删）",
                    "derived": False,
                    "proposer": "your-name",
                    "proposed_at": now,
                    "status": "PROPOSED",
                }
            }
        },
        "classes.yaml": {
            "classes": {
                "COND": {
                    "name_cn": "环境条件",
                    "owner": "your-name",
                    "scope": "温度/湿度/气氛等环境参数",
                    "description": "示例 class，可删",
                    "proposer": "your-name",
                    "proposed_at": now,
                    "status": "PROPOSED",
                }
            }
        },
        "codes.yaml": {
            "codes": {
                "COND1": {
                    "class": "COND",
                    "instance": "23±1 °C，常压，室内气氛（示例，可删）",
                    "proposer": "your-name",
                    "proposed_at": now,
                    "status": "PROPOSED",
                }
            }
        },
        "classification.yaml": {
            "classification": {"default": "internal", "types": {}}
        },
        "signatures.yaml": {"signatures": []},
    }
    written = []
    for filename, data in files.items():
        p = path / filename
        if p.exists() and not force:
            continue
        _write_yaml(p, data)
        written.append(p)
    return written
