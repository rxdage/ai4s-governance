#!/usr/bin/env python
"""Build a synthetic messy lab folder for `ai4s audit` demos and tests.

No real data. The names are drawn from the failure modes in the playbook:
short IDs, Chinese/space names, version names, instrument names, serials,
unregistered types, missing extensions, and duplicate names.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import List, Tuple


def _write(root: Path, name: str, text: str = "synthetic\n") -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build(dest: Path, force: bool = False) -> List[Tuple[str, int]]:
    dest = Path(dest)
    if dest.exists() and any(dest.iterdir()):
        if not force:
            raise FileExistsError(f"{dest} is not empty (use --force)")
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)

    counts: List[Tuple[str, int]] = []

    # 1. short / unpadded IDs
    n = 0
    for i in range(30):
        _write(dest, f"R37_W1_D{i:04d}__MEAS__NA__T202603041430_RUN0000.csv")
        n += 1
    counts.append(("short_ids", n))

    # 2. Chinese + hyphen + space
    n = 0
    for i in range(20):
        _write(dest, f"R0037-W01-{i:02d}_after 丙酮擦拭.jpg")
        n += 1
    counts.append(("chinese_space", n))

    # 3. version names
    n = 0
    for i in range(10):
        _write(dest, f"final_v{i}.csv")
        n += 1
    for name in ("final_final.csv", "copy of data.csv", "最新汇总.xlsx", "backup_old.csv", "data_new.csv"):
        _write(dest, name)
        n += 1
    counts.append(("version_names", n))

    # 4. instrument auto-names
    n = 0
    for i in range(15):
        _write(dest, f"Channel_{i:02d}_for_filterData_2026-07-22-17-00-31.csv")
        n += 1
    counts.append(("instrument_names", n))

    # 5. pure serials
    n = 0
    for i in range(15):
        _write(dest, f"dna{i:03d}.abf")
        n += 1
    counts.append(("serials", n))

    # 6. syntactically valid but unregistered type
    n = 0
    for i in range(10):
        _write(dest, f"R0007_W0012_D{i:04d}__XYZ__NA__T202603041430_RUN0000.csv")
        n += 1
    counts.append(("valid_unregistered", n))

    # 7. no extension
    n = 0
    for i in range(5):
        _write(dest, f"R0007_W0012_D{i:04d}__MEAS__NA__T202603041430_RUN0000")
        n += 1
    counts.append(("no_extension", n))

    # 8. duplicate full names in a subfolder
    n = 0
    for i in range(5):
        name = f"R0007_W0012_D{i:04d}__XYZ__NA__T202603041430_RUN0000.csv"
        _write(dest / "archive", name)
        n += 1
    counts.append(("duplicates", n))

    return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", default="examples/messy-lab")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        rows = build(Path(args.dir), force=args.force)
    except FileExistsError as exc:
        print(f"error: {exc}\nrun with --force to rebuild.")
        raise SystemExit(1)
    total = sum(count for _, count in rows)
    for label, count in rows:
        print(f"{label:22} {count}")
    print(f"{'total':22} {total}")
