#!/usr/bin/env python
"""Check that relative Markdown links point at files that exist.

Skips fenced code blocks, absolute URLs, anchors and mail links. Exits 1 on a
broken link. Good enough for a docs repo; not a full CommonMark parser.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import List

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
FENCE_RE = re.compile(r"```.*?```", re.S)


def strip_fences(text: str) -> str:
    return FENCE_RE.sub("", text)


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", default=".", help="repository root")
    args = parser.parse_args(argv)
    root = Path(args.path).resolve()
    broken = []
    checked = 0
    for md in root.rglob("*.md"):
        if any(part in {".git", ".venv", "node_modules", "examples"} for part in md.parts):
            continue
        text = strip_fences(md.read_text(encoding="utf-8", errors="ignore"))
        for match in LINK_RE.finditer(text):
            target = match.group(1)
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            clean = target.split("#", 1)[0]
            if not clean:
                continue
            checked += 1
            if not (md.parent / clean).resolve().exists():
                broken.append(f"{md.relative_to(root)} -> {target}")
    for row in broken:
        print(row)
    print(f"{checked} local link(s), {len(broken)} broken")
    return 0 if not broken else 1


if __name__ == "__main__":
    raise SystemExit(main())
