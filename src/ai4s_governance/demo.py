"""Build a small, self-consistent demo lab.

The demo is generated rather than committed so that hashes in sidecars always
match the files. It exercises the whole loop: registry → signature → delivery →
self-check → ingest → derived gate → verify → patrol.
"""

from __future__ import annotations

import hashlib
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import yaml

from . import ingest, naming, patrol, selfcheck
from .registry import Registry, load_registry

DEMO_WHO = "Demo Maintainer"
DEMO_REVIEWER = "Demo Reviewer"
DEMO_DATE = "2026-03-04"

TYPES = {
    "MEAS": {
        "name_cn": "测量数据",
        "description": "仪器直接产出的一次采集",
        "derived": False,
        "proposer": DEMO_WHO,
        "proposed_at": DEMO_DATE,
        "status": "PROPOSED",
    },
    "IMG": {
        "name_cn": "图像",
        "description": "相机/扫描类仪器产出的图像",
        "derived": False,
        "proposer": DEMO_WHO,
        "proposed_at": DEMO_DATE,
        "status": "PROPOSED",
    },
    "SUMMARY": {
        "name_cn": "汇总结果",
        "description": "从多个测量文件算出来的汇总表",
        "derived": True,
        "proposer": DEMO_WHO,
        "proposed_at": DEMO_DATE,
        "status": "PROPOSED",
    },
    "CALIB": {
        "name_cn": "校准记录",
        "description": "仪器校准与标定记录",
        "derived": False,
        "proposer": DEMO_WHO,
        "proposed_at": DEMO_DATE,
        "status": "PROPOSED",
    },
}

CLASSES = {
    "BUF": {
        "name_cn": "缓冲液",
        "owner": DEMO_WHO,
        "scope": "缓冲液配方与浓度",
        "description": "湿实验的缓冲液条件",
        "proposer": DEMO_WHO,
        "proposed_at": DEMO_DATE,
        "status": "PROPOSED",
    },
    "DAQ": {
        "name_cn": "采集设置",
        "owner": DEMO_WHO,
        "scope": "采样率、滤波、量程",
        "description": "数据采集的仪器设置",
        "proposer": DEMO_WHO,
        "proposed_at": DEMO_DATE,
        "status": "PROPOSED",
    },
    "COND": {
        "name_cn": "环境条件",
        "owner": DEMO_WHO,
        "scope": "温度、湿度、气氛",
        "description": "实验环境",
        "proposer": DEMO_WHO,
        "proposed_at": DEMO_DATE,
        "status": "PROPOSED",
    },
}

CODES = {
    "BUF1": {
        "class": "BUF",
        "instance": "10 mM Tris-HCl, pH 8.0, 1 M KCl（示例）",
        "proposer": DEMO_WHO,
        "proposed_at": DEMO_DATE,
        "status": "PROPOSED",
    },
    "DAQ1": {
        "class": "DAQ",
        "instance": "100 kS/s, 5 kHz low-pass, ±1 V range（示例）",
        "proposer": DEMO_WHO,
        "proposed_at": DEMO_DATE,
        "status": "PROPOSED",
    },
    "COND1": {
        "class": "COND",
        "instance": "23 ± 1 °C, ambient, 45–55% RH（示例）",
        "proposer": DEMO_WHO,
        "proposed_at": DEMO_DATE,
        "status": "PROPOSED",
    },
}


def _yaml(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _rmtree_writable(path: Path) -> None:
    """Windows: library files are read-only; clear the flag before deleting."""
    for item in path.rglob("*"):
        try:
            item.chmod(0o666)
        except OSError:
            pass
    shutil.rmtree(path)


def build(dest: Path, force: bool = False) -> Dict[str, Any]:
    dest = Path(dest).resolve()
    if dest.exists() and any(dest.iterdir()):
        if not force:
            raise FileExistsError(f"{dest} is not empty (use --force)")
        _rmtree_writable(dest)
    dest.mkdir(parents=True, exist_ok=True)

    # schema copy so the demo is self-contained
    schema_src = naming.find_schema()
    (dest / "spec").mkdir(exist_ok=True)
    shutil.copyfile(schema_src, dest / "spec" / "filename-schema.yaml")

    # registry
    reg_dir = dest / "registry"
    _yaml(reg_dir / "types.yaml", {"types": TYPES})
    _yaml(reg_dir / "classes.yaml", {"classes": CLASSES})
    _yaml(reg_dir / "codes.yaml", {"codes": CODES})
    _yaml(
        reg_dir / "classification.yaml",
        {"classification": {"default": "internal", "types": {"SUMMARY": "internal"}}},
    )
    _yaml(reg_dir / "signatures.yaml", {"signatures": []})
    reg = load_registry(reg_dir, schema=naming.load_schema(dest / "spec" / "filename-schema.yaml"))
    reg.sign("type", list(TYPES), DEMO_WHO, DEMO_DATE, apply=True)
    reg.sign("class", list(CLASSES), DEMO_WHO, DEMO_DATE, apply=True)
    reg.sign("code", list(CODES), DEMO_WHO, DEMO_DATE, apply=True)
    reg = load_registry(reg_dir, schema=naming.load_schema(dest / "spec" / "filename-schema.yaml"))
    check = reg.check()
    if check.errors:
        raise RuntimeError("demo registry does not verify: " + str([i.to_dict() for i in check.errors]))

    # workspace
    ws = dest / "workspaces" / "owner-a"
    sr_data = ws / "SR_DATA"
    for sub in ("SR_DATA", "REGISTRY", "LIVEDOCS", "PERSONAL"):
        (ws / sub).mkdir(parents=True, exist_ok=True)
    (dest / "workspaces" / "steward" / "SR_DATA").mkdir(parents=True, exist_ok=True)

    meas0 = "R0001_W0001_D0001__MEAS__BUF1_DAQ1__T202603041030_RUN0000.csv"
    meas1 = "R0001_W0001_D0001__MEAS__BUF1_DAQ1__T202603041045_RUN0001.csv"
    img = "R0001_W0001_D0001__IMG__COND1__T202603041100_RUN0000.png"
    (sr_data / meas0).write_text(
        "identity,value\nR0001_W0001_D0001,0.41\n", encoding="utf-8"
    )
    (sr_data / meas1).write_text(
        "identity,value\nR0001_W0001_D0001,0.43\n", encoding="utf-8"
    )
    (sr_data / img).write_bytes(
        b"\x89PNG\r\n\x1a\n" + b"demo-image-not-a-real-png" * 4
    )

    # first delivery: raw files
    first = selfcheck.check_delivery(sr_data, reg)
    if not first.ok:
        raise RuntimeError("demo raw delivery failed: " + selfcheck.format_summary(first))

    library = dest / "library"
    ingest.copy(sr_data, library, reg, apply=True, batch="20260304-01")
    manifest = ingest.manifest_sha_map(library)

    # derived file + sidecar
    summary_name = "R0001_W0001_ALL__SUMMARY__NA__T202603051200_RUN0000.csv"
    summary = sr_data / summary_name
    summary.write_text(
        "identity,metric,value\nR0001_W0001_ALL,mean,0.42\n", encoding="utf-8"
    )
    sidecar = summary.with_name(summary.name + ".meta.yaml")
    _yaml(
        sidecar,
        {
            "derived_from": [meas0, meas1],
            "input_sha256": [manifest[meas0], manifest[meas1]],
            "method": "script",
            "tool": "examples/make_summary.py @ demo",
            "params": {"metric": "mean"},
            "reviewed_by": DEMO_REVIEWER,
            "reviewed_at": "2026-03-05",
        },
    )

    second = selfcheck.check_delivery(sr_data, reg, manifest=manifest)
    if not second.ok:
        raise RuntimeError("demo derived delivery failed: " + selfcheck.format_summary(second))

    ingest.copy(sr_data, library, reg, apply=True, batch="20260305-01")
    verified = ingest.verify(library)
    if not verified.ok:
        raise RuntimeError("demo library does not verify: " + str(verified.to_dict()))

    lab = {
        "lab": {"name": "demo-lab", "timezone": "UTC"},
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
        "bot": {
            "adapter": "console",
            "dry_run": True,
            "state_dir": "state",
            "steward": "steward",
        },
    }
    _yaml(dest / "lab.yaml", lab)

    status = patrol.run(dest / "lab.yaml")
    return {
        "dest": str(dest),
        "files": second.files,
        "warnings": len(second.warnings),
        "manifest_rows": len(ingest.read_manifest(library)),
        "patrol_blocked": status["summary"]["blocked"],
    }
