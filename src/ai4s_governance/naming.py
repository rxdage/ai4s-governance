"""Four-zone filename parser and validator.

The grammar is loaded from ``spec/filename-schema.yaml`` so the machine
contract and the implementation cannot drift apart silently.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

import yaml

SCHEMA_ENV = "AI4S_SCHEMA"
DEFAULT_SCHEMA_REL = Path("spec") / "filename-schema.yaml"


# ---------------------------------------------------------------------------
# schema loading
# ---------------------------------------------------------------------------
def find_schema(start: Optional[Path] = None) -> Path:
    """Locate the machine contract.

    Order: explicit start path -> $AI4S_SCHEMA -> repo-relative -> cwd.
    """
    if start:
        p = Path(start)
        if p.is_dir():
            p = p / "filename-schema.yaml"
        if p.is_file():
            return p
        raise FileNotFoundError(f"schema not found: {start}")

    env = os.environ.get(SCHEMA_ENV)
    if env:
        p = Path(env)
        if p.is_file():
            return p
        raise FileNotFoundError(f"{SCHEMA_ENV} points to a missing file: {env}")

    here = Path(__file__).resolve()
    for parent in here.parents:
        p = parent / DEFAULT_SCHEMA_REL
        if p.is_file():
            return p
    p = Path.cwd() / DEFAULT_SCHEMA_REL
    if p.is_file():
        return p
    raise FileNotFoundError(
        "filename-schema.yaml not found; pass --schema or set AI4S_SCHEMA"
    )


def load_schema(path: Optional[Path] = None) -> Dict[str, Any]:
    p = find_schema(path)
    with p.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict) or "zones" not in data:
        raise ValueError(f"not a filename schema: {p}")
    return data


# ---------------------------------------------------------------------------
# result types
# ---------------------------------------------------------------------------
@dataclass
class Issue:
    code: str
    severity: str
    message: str
    hint: str = ""

    def to_dict(self) -> Dict[str, str]:
        out = {"code": self.code, "severity": self.severity, "message": self.message}
        if self.hint:
            out["hint"] = self.hint
        return out


@dataclass
class ParsedName:
    raw: str
    ok: bool = False
    batch: Optional[int] = None
    sample: Optional[str] = None
    unit: Optional[str] = None
    type_code: Optional[str] = None
    conditions: List[str] = field(default_factory=list)
    timestamp: Optional[str] = None
    run: Optional[int] = None
    ext: Optional[str] = None
    partition: Optional[str] = None
    issues: List[Issue] = field(default_factory=list)
    warnings: List[Issue] = field(default_factory=list)

    @property
    def errors(self) -> List[Issue]:
        return [i for i in self.issues if i.severity == "ERROR"]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.raw,
            "ok": self.ok,
            "batch": self.batch,
            "sample": self.sample,
            "unit": self.unit,
            "type_code": self.type_code,
            "conditions": list(self.conditions),
            "timestamp": self.timestamp,
            "run": self.run,
            "ext": self.ext,
            "partition": self.partition,
            "errors": [i.to_dict() for i in self.issues],
            "warnings": [i.to_dict() for i in self.warnings],
        }


@dataclass
class ZonePatterns:
    zone1: re.Pattern
    zone2: re.Pattern
    zone3: re.Pattern
    zone4: re.Pattern
    extension: re.Pattern

    @classmethod
    def from_schema(cls, schema: Mapping[str, Any]) -> "ZonePatterns":
        zones = schema["zones"]

        def full(pattern: str) -> re.Pattern:
            return re.compile("^(?:" + pattern + ")$")

        return cls(
            zone1=full(zones["zone1"]["pattern"]),
            zone2=full(zones["zone2"]["pattern"]),
            zone3=full(zones["zone3"]["pattern"]),
            zone4=full(zones["zone4"]["pattern"]),
            extension=full(zones["extension"]["pattern"]),
        )


def _issue(code: str, severity: str, message: str, hint: str = "") -> Issue:
    return Issue(code=code, severity=severity, message=message, hint=hint)


def _err(res: ParsedName, code: str, message: str, hint: str = "") -> None:
    res.issues.append(_issue(code, "ERROR", message, hint))


def _warn(res: ParsedName, code: str, message: str, hint: str = "") -> None:
    res.warnings.append(_issue(code, "WARN", message, hint))


def _entry_state(entry: Mapping[str, Any]) -> str:
    return str(entry.get("_signature_state", "missing"))


def _is_usable(entry: Mapping[str, Any]) -> bool:
    effective = entry.get("_effective_status")
    if effective is not None:
        return effective == "APPROVED"
    return entry.get("status") == "APPROVED" and _entry_state(entry) == "valid"


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------
def parse(
    name: str,
    registry: Optional[Mapping[str, Any]] = None,
    schema: Optional[Mapping[str, Any]] = None,
    check_registry: bool = True,
) -> ParsedName:
    """Parse one filename. Never raises on bad names; returns issues instead."""
    sch = schema or load_schema()
    pats = ZonePatterns.from_schema(sch)
    res = ParsedName(raw=name)
    text = name.strip("\r\n")

    if not text:
        _err(res, "ZONE_COUNT", "文件名是空的")
        return _finish(res)

    if len(text.encode("utf-8")) > int(sch["max_name_bytes"]):
        _err(
            res,
            "NAME_TOO_LONG",
            f"文件名 {len(text.encode('utf-8'))} 字节，超过上限 {sch['max_name_bytes']}",
            "缩短类型码/条件码，或拆成多个文件",
        )

    charset = str(sch.get("charset", "A-Za-z0-9_."))
    if not re.fullmatch("[" + charset + "]+", text):
        bad = sorted({ch for ch in text if not re.fullmatch("[" + charset + "]", ch)})
        _err(
            res,
            "CHARSET_INVALID",
            f"出现非法字符：{''.join(bad)!r}",
            "只允许 A-Z 0-9 下划线和扩展名里的点；空格、连字符、中文、括号都不行",
        )
        return _finish(res)

    if "_RUN" in text and re.search(r"_RUN[0-9]{4}_P[0-9]{4}(?:\.|$)", text):
        _err(
            res,
            "LEGACY_P_SLOT",
            "使用了已取消的 P 槽位",
            "第 4 区只有 T + RUN 两段；同一次采集多个文件用递增 RUN 区分",
        )

    zones = text.split(sch["zone_separator"])
    if len(zones) != int(sch["zone_count"]):
        _err(
            res,
            "ZONE_COUNT",
            f"按 '__' 切出 {len(zones)} 段，要求 {sch['zone_count']} 段",
            "R0007_W0012_D0003__MEAS__BUF1__T202603041430_RUN0000.csv",
        )
        return _finish(res)

    z1, z2, z3, z4 = zones

    if sch.get("uppercase_body", True):
        stem = z4.split(".", 1)[0]
        lowered = [part for part in (z1, z2, z3, stem) if part != part.upper()]
        if lowered:
            _err(
                res,
                "BODY_NOT_UPPERCASE",
                f"区内容必须全大写：{lowered}",
                "只有扩展名允许小写；不要靠大小写区分语义",
            )

    # zone 1 ---------------------------------------------------------------
    m1 = pats.zone1.match(z1)
    if not m1:
        _err(
            res,
            "ZONE1_SYNTAX",
            f"身份区 {z1!r} 形状不对",
            "必须是 R####_W####_D####；整片用 W####_ALL；整批用 ALL_ALL；库级用 R0000_ALL_ALL",
        )
        return _finish(res)

    res.batch = int(m1.group("batch"))
    res.sample = m1.group("sample")
    res.unit = m1.group("unit")
    all_token = str(sch["zones"]["zone1"].get("all_token", "ALL"))
    lib = sch.get("semantics", {}).get("library", {})
    numbering = sch.get("semantics", {}).get("numbering", {})

    if res.sample == all_token and res.unit != all_token:
        _err(res, "ZONE1_ALL_MIX", "W=ALL 时 D 必须也是 ALL")
    if res.batch == int(lib.get("batch", 0)) and not (
        res.sample == all_token and res.unit == all_token
    ):
        _err(res, "ZONE1_LIBRARY_MIX", "R0000 是库级专用形态，W 和 D 都必须写 ALL")

    zero_from = int(numbering.get("zero_allowed_from", 1))
    legacy_min = int(numbering.get("legacy_min", 1))
    minimum = 0 if res.batch >= zero_from else legacy_min
    for label, value in (("W", res.sample), ("D", res.unit)):
        if value == all_token:
            continue
        num = int(value[1:])
        if num < minimum:
            _err(
                res,
                "ZONE1_NUMBERING",
                f"{label}{num:04d} 低于该批次允许的最小值 {minimum:04d}",
                f"batch < {zero_from} 的历史批次从 {legacy_min:04d} 起编",
            )

    # zone 2 ---------------------------------------------------------------
    m2 = pats.zone2.match(z2)
    if not m2:
        _err(
            res,
            "TYPE_SYNTAX",
            f"类型码 {z2!r} 不合法",
            "2–15 个纯大写字母，不含数字；条件才带数字",
        )
    else:
        res.type_code = m2.group("type_code")

    # zone 3 ---------------------------------------------------------------
    _parse_conditions(res, z3, pats, sch)

    # zone 4 + extension ---------------------------------------------------
    if "." not in z4:
        _err(res, "EXT_MISSING", "第 4 区后面缺少扩展名")
    else:
        stem, dot, ext_tail = z4.partition(".")
        ext = "." + ext_tail
        m4 = pats.zone4.match(stem)
        if not m4:
            _err(
                res,
                "ZONE4_SYNTAX",
                f"时序区 {stem!r} 不合法",
                "必须是 T##########_RUN####（12 位时间 + 4 位轮次）",
            )
        else:
            res.timestamp = m4.group("timestamp")
            res.run = int(m4.group("run"))
            _check_time(res, sch)
        if not pats.extension.match(ext):
            _err(res, "EXT_MISSING", f"扩展名 {ext!r} 不合法")
        else:
            res.ext = ext

    # registry -------------------------------------------------------------
    if check_registry and registry is not None and res.type_code:
        _check_registry(res, registry)

    return _finish(res)


def _parse_conditions(
    res: ParsedName,
    z3: str,
    pats: ZonePatterns,
    sch: Mapping[str, Any],
) -> None:
    none_token = str(sch["zones"]["zone3"].get("none_token", "NA"))
    if z3 == none_token:
        return
    if not pats.zone3.match(z3):
        if none_token in z3.split("_"):
            _err(res, "COND_NA_MIXED", f"NA 必须独占整个第三区，不能和别的码混写：{z3!r}")
        else:
            _err(
                res,
                "CODE_SYNTAX",
                f"条件区 {z3!r} 不合法",
                "写成 CLASS+数字，如 BUF1；多个用单下划线连接，如 BUF1_DAQ1",
            )
        return

    codes = z3.split(sch["intra_zone_separator"])
    max_codes = int(sch["zones"]["zone3"].get("max_codes", 8))
    if len(codes) > max_codes:
        _err(res, "COND_TOO_MANY", f"条件码 {len(codes)} 个，上限 {max_codes}")

    class_re = re.compile(str(sch["zones"]["zone3"]["class_pattern"]))
    seen: Dict[str, str] = {}
    for code in codes:
        m = class_re.match(code)
        if not m:
            _err(res, "CODE_SYNTAX", f"条件码 {code!r} 不合法")
            continue
        cls = m.group("cls")
        if cls in seen:
            _err(
                res,
                "COND_DUPLICATE_CLASS",
                f"class {cls} 出现了两次（{seen[cls]} 和 {code}）",
                "同一个 class 在一个名字里最多一次",
            )
        seen[cls] = code
        res.conditions.append(code)

    if res.conditions != sorted(res.conditions):
        _warn(
            res,
            "COND_ORDER",
            f"条件码未按 ASCII 排序：{'/'.join(res.conditions)}",
            f"建议写成 {'_'.join(sorted(res.conditions))}；改不改由人决定",
        )


def _check_time(res: ParsedName, sch: Mapping[str, Any]) -> None:
    fmt = str(sch.get("semantics", {}).get("time_format", "%Y%m%d%H%M"))
    lo = int(sch.get("semantics", {}).get("time_min_year", 2000))
    hi = int(sch.get("semantics", {}).get("time_max_year", 2099))
    assert res.timestamp
    try:
        dt = datetime.strptime(res.timestamp, fmt)
    except ValueError:
        _err(
            res,
            "TIME_INVALID",
            f"T={res.timestamp} 不是真实日期时间",
            "布局是 YYYYMMDDHHMM，人工核对后手写，不取自动生成的创建时间",
        )
        return
    if not (lo <= dt.year <= hi):
        _err(res, "TIME_OUT_OF_RANGE", f"T 的年份 {dt.year} 超出 {lo}–{hi}")


def _check_registry(res: ParsedName, registry: Mapping[str, Any]) -> None:
    types = registry.get("types") or {}
    classes = registry.get("classes") or {}
    codes = registry.get("codes") or {}

    t = types.get(res.type_code)
    if not t:
        _err(
            res,
            "TYPE_UNKNOWN",
            f"类型码 {res.type_code} 未注册",
            "先在 registry/types.yaml 提案并签字，不得先用后补",
        )
    elif t.get("status") == "DEPRECATED":
        sup = t.get("superseded_by") or "（无接替号，先问维护者）"
        _err(res, "TYPE_DEPRECATED", f"类型码 {res.type_code} 已作废", f"接替：{sup}")
    elif _entry_state(t) == "stale":
        _err(
            res,
            "SIGNATURE_STALE",
            f"类型码 {res.type_code} 的签名已失效（内容改过）",
            "重新签字后才能用于新文件",
        )
    elif not _is_usable(t):
        _err(res, "TYPE_NOT_APPROVED", f"类型码 {res.type_code} 尚未签字批准")
    elif t.get("derived") is True:
        res.partition = "derived"
    elif t.get("derived") is False:
        res.partition = "data"

    for code in res.conditions:
        c = codes.get(code)
        if not c:
            _err(res, "CODE_UNKNOWN", f"条件码 {code} 未注册")
            continue
        cls = str(c.get("class", ""))
        if cls not in classes:
            _err(res, "CLASS_MISSING", f"条件码 {code} 指向的 class {cls} 不存在")
            continue
        if not code.startswith(cls):
            _err(res, "CODE_SYNTAX", f"条件码 {code} 与 class {cls} 不匹配")
        if c.get("status") == "DEPRECATED":
            _err(res, "CODE_DEPRECATED", f"条件码 {code} 已作废")
        elif _entry_state(c) == "stale":
            _err(res, "SIGNATURE_STALE", f"条件码 {code} 的签名已失效（内容改过）")
        elif not _is_usable(c):
            _err(res, "CODE_NOT_APPROVED", f"条件码 {code} 尚未签字批准")
        elif not _is_usable(classes[cls]):
            _err(res, "CODE_NOT_APPROVED", f"条件码 {code} 所属的 class {cls} 尚未签字批准")


def _finish(res: ParsedName) -> ParsedName:
    res.ok = not res.errors
    return res


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def parse_many(
    names: Iterable[str],
    registry: Optional[Mapping[str, Any]] = None,
    schema: Optional[Mapping[str, Any]] = None,
) -> List[ParsedName]:
    return [parse(n, registry=registry, schema=schema) for n in names]


def sample_name(
    batch: int = 7,
    sample: int = 12,
    unit: int = 3,
    type_code: str = "MEAS",
    conditions: str = "BUF1",
    timestamp: str = "202603041430",
    run: int = 0,
    ext: str = ".csv",
) -> str:
    return (
        f"R{batch:04d}_W{sample:04d}_D{unit:04d}__{type_code}__{conditions}"
        f"__T{timestamp}_RUN{run:04d}{ext}"
    )


def effective_status(entry: Mapping[str, Any]) -> str:
    """Public helper used by CLIs/docs: APPROVED only when the signature holds."""
    if entry.get("_effective_status"):
        return str(entry["_effective_status"])
    if entry.get("status") == "DEPRECATED":
        return "DEPRECATED"
    if _is_usable(entry):
        return "APPROVED"
    if _entry_state(entry) == "stale":
        return "SIGNATURE_STALE"
    return "PROPOSED"


# ---------------------------------------------------------------------------
# selftest
# ---------------------------------------------------------------------------
_SELFTEST_REGISTRY: Dict[str, Any] = {
    "types": {
        "MEAS": {"status": "APPROVED", "_signature_state": "valid", "derived": False},
        "SUM": {"status": "APPROVED", "_signature_state": "valid", "derived": True},
        "OLD": {
            "status": "DEPRECATED",
            "_signature_state": "n/a",
            "derived": False,
            "superseded_by": "MEAS",
        },
        "WAIT": {"status": "PROPOSED", "_signature_state": "missing", "derived": False},
        "STALE": {"status": "PROPOSED", "_signature_state": "stale", "derived": False},
    },
    "classes": {
        "BUF": {"status": "APPROVED", "_signature_state": "valid"},
        "DAQ": {"status": "APPROVED", "_signature_state": "valid"},
        "COND": {"status": "APPROVED", "_signature_state": "valid"},
    },
    "codes": {
        "BUF1": {"class": "BUF", "status": "APPROVED", "_signature_state": "valid"},
        "BUF2": {"class": "BUF", "status": "APPROVED", "_signature_state": "valid"},
        "DAQ1": {"class": "DAQ", "status": "APPROVED", "_signature_state": "valid"},
        "COND1": {"class": "COND", "status": "APPROVED", "_signature_state": "valid"},
    },
}

_POSITIVES = [
    "R0007_W0012_D0003__MEAS__BUF1_DAQ1__T202603041430_RUN0000.csv",
    "R0007_W0012_ALL__MEAS__NA__T202603041430_RUN0000.xlsx",
    "R0007_ALL_ALL__MEAS__NA__T202603041430_RUN0000.md",
    "R0000_ALL_ALL__SUM__NA__T202603041430_RUN0000.csv",
    "R0007_W0012_D0003__MEAS__NA__T202402291200_RUN0001.abf",
    "R0007_W0012_D0003__MEAS__BUF1__T202603041430_RUN0000.rt.stdout",
    "R0007_W0000_D0000__MEAS__NA__T202603041430_RUN0000.csv",
]

_NEGATIVES = {
    "R7_W12_D3__MEAS__NA__T202603041430_RUN0000.csv": "ZONE1_SYNTAX",
    "R0007_ALL_D0003__MEAS__NA__T202603041430_RUN0000.csv": "ZONE1_ALL_MIX",
    "R0000_W0012_D0003__MEAS__NA__T202603041430_RUN0000.csv": "ZONE1_LIBRARY_MIX",
    "R0007_W0012_D0003__MEAS__BUF01__T202603041430_RUN0000.csv": "CODE_SYNTAX",
    "R0007_W0012_D0003__MEAS__BUF1_BUF2__T202603041430_RUN0000.csv": "COND_DUPLICATE_CLASS",
    "R0007_W0012_D0003__MEAS__NA_BUF1__T202603041430_RUN0000.csv": "COND_NA_MIXED",
    "R0007_W0012_D0003__meas__NA__T202603041430_RUN0000.csv": "BODY_NOT_UPPERCASE",
    "R0007_W0012_D0003__MEAS__NA__T202613041430_RUN0000.csv": "TIME_INVALID",
    "R0007_W0012_D0003__MEAS__NA__T202603041430_RUN0000_P0000.csv": "LEGACY_P_SLOT",
    "R0007_W0012_D0003__MEAS__NA__T202603041430_RUN0000": "EXT_MISSING",
    "R0007-W0012-D0003__MEAS__NA__T202603041430_RUN0000.csv": "CHARSET_INVALID",
    "R0000_W0012_D0003__MEAS__NA__T202603041430_RUN0000.csv": "ZONE1_LIBRARY_MIX",
}


def selftest(verbose: bool = False) -> int:
    failures = 0
    schema = load_schema()
    for name in _POSITIVES:
        r = parse(name, registry=_SELFTEST_REGISTRY, schema=schema)
        if not r.ok:
            failures += 1
            print(f"[FAIL+] {name}")
            for i in r.errors:
                print(f"        {i.code}: {i.message}")
        elif verbose:
            print(f"[ok+] {name}")

    for name, expected in _NEGATIVES.items():
        r = parse(name, registry=_SELFTEST_REGISTRY, schema=schema)
        got = [i.code for i in r.errors]
        if expected not in got:
            failures += 1
            print(f"[FAIL-] {name}\n        expected {expected}, got {got}")
        elif verbose:
            print(f"[ok-] {name} -> {expected}")

    # legacy numbering: zero is only legal from a configured batch onwards
    import copy

    legacy_schema = copy.deepcopy(schema)
    legacy_schema["semantics"]["numbering"]["zero_allowed_from"] = 39
    r = parse(
        "R0038_W0000_D0001__MEAS__NA__T202603041430_RUN0000.csv",
        registry=_SELFTEST_REGISTRY,
        schema=legacy_schema,
    )
    if "ZONE1_NUMBERING" not in [i.code for i in r.errors]:
        failures += 1
        print("[FAIL-] legacy numbering not enforced")

    # registry semantics
    for name, expected in (
        ("R0007_W0012_D0003__WAIT__NA__T202603041430_RUN0000.csv", "TYPE_NOT_APPROVED"),
        ("R0007_W0012_D0003__STALE__NA__T202603041430_RUN0000.csv", "SIGNATURE_STALE"),
        ("R0007_W0012_D0003__OLD__NA__T202603041430_RUN0000.csv", "TYPE_DEPRECATED"),
        ("R0007_W0012_D0003__NOPE__NA__T202603041430_RUN0000.csv", "TYPE_UNKNOWN"),
    ):
        r = parse(name, registry=_SELFTEST_REGISTRY, schema=schema)
        got = [i.code for i in r.errors]
        if expected not in got:
            failures += 1
            print(f"[FAIL-] {name}\n        expected {expected}, got {got}")

    if failures:
        print(f"selftest: {failures} failure(s)")
        return 1
    print(
        f"selftest: OK ({len(_POSITIVES)} positives, "
        f"{len(_NEGATIVES) + 5} negatives)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(selftest(verbose=True))
