#!/usr/bin/env python
"""Build the demo lab under examples/demo (generated, not committed)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ai4s_governance.demo import build  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="delete and rebuild")
    args = parser.parse_args()
    dest = Path(__file__).resolve().parent / "demo"
    try:
        info = build(dest, force=args.force)
    except FileExistsError as exc:
        print(f"error: {exc}\nrun `python examples/build_demo.py --force` to rebuild.")
        raise SystemExit(1)
    for key, value in info.items():
        print(f"{key}: {value}")
