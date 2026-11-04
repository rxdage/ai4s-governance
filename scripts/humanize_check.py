#!/usr/bin/env python
"""Flag the most common AI-writing tells in human-facing prose.

This is a tripwire, not a judge. It cannot tell good writing from bad; it only
finds the patterns that make a draft read like a model talking to a model.

Usage:
    python scripts/humanize_check.py --path .
    python scripts/humanize_check.py --path . --strict   # fail on shop-window files
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Pattern, Tuple

# Files that a visitor reads first. `--strict` fails only on these.
SHOP_WINDOW = [
    "README.md",
    "README.zh-CN.md",
    "docs/00-overview.md",
    "docs/13-evolution.md",
    "docs/14-adoption.md",
    "docs/15-agent-ops.md",
    "docs/field-notes/01-the-changelog-is-the-product.md",
    "docs/field-notes/02-how-fast-do-five-scientists-adopt.md",
    "docs/field-notes/03-the-strongest-model-is-not-the-router.md",
    "docs/field-notes/04-a-folder-that-looks-organized.md",
]

EXCLUDE = {
    "docs/16-writing.md",  # quotes bad examples on purpose
    "scripts/humanize_check.py",
}

PATTERNS: List[Tuple[str, Pattern[str]]] = [
    ("not_x_but_y", re.compile(r"不是.{0,30}(?:而是|，是)")),
    ("not_only_but_also", re.compile(r"不仅.{0,30}而且")),
    ("really_is", re.compile(r"真正的.{0,12}(?:是|不是)")),
    ("essence", re.compile(r"本质上|归根结底|换句话说|值得注意的是|总的来说|综上所述|总而言之")),
    ("trend_opening", re.compile(r"随着.{0,20}(?:发展|到来|普及)|在当今")),
    ("let_us", re.compile(r"让我们")),
    ("triad", re.compile(r"首先.{0,60}其次.{0,60}最后")),
    ("en_not_just", re.compile(r"\bnot just\b", re.I)),
    ("en_not_only", re.compile(r"\bnot only\b", re.I)),
    ("en_not_x_it_y", re.compile(r"\bit'?s not .{0,60}? it'?s\b", re.I)),
    ("en_delve", re.compile(r"\bdelve\b", re.I)),
    ("en_seamless", re.compile(r"\bseamless(?:ly)?\b", re.I)),
    ("en_leverage", re.compile(r"\bleverage\b", re.I)),
    ("en_unlock", re.compile(r"\bunlock\b", re.I)),
    ("en_empower", re.compile(r"\bempower\b", re.I)),
    ("en_game_changer", re.compile(r"\bgame[- ]changer\b", re.I)),
    ("en_in_todays", re.compile(r"\bin today'?s\b", re.I)),
    ("en_lets_dive", re.compile(r"\blet'?s dive\b", re.I)),
    ("en_heres_the_thing", re.compile(r"\bhere'?s the thing\b", re.I)),
]

FENCE_RE = re.compile(r"```.*?```", re.S)


@dataclass
class FileResult:
    path: str
    hits: List[Dict[str, object]] = field(default_factory=list)
    dashes: int = 0

    def to_dict(self) -> Dict[str, object]:
        return {"path": self.path, "hits": self.hits, "em_dashes": self.dashes}


def _strip_fences(text: str) -> str:
    return FENCE_RE.sub("", text)


def check_file(path: Path, root: Path) -> FileResult:
    rel = str(path.relative_to(root)).replace("\\", "/")
    result = FileResult(path=rel)
    text = _strip_fences(path.read_text(encoding="utf-8", errors="ignore"))
    result.dashes = text.count("——")
    for lineno, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        if "humanize:ignore" in line:
            continue
        for name, rx in PATTERNS:
            if rx.search(line):
                preview = " ".join(line.strip().split())
                if len(preview) > 100:
                    preview = preview[:99] + "…"
                result.hits.append({"line": lineno, "kind": name, "text": preview})
    return result


def iter_markdown(root: Path) -> Iterable[Path]:
    for path in root.rglob("*.md"):
        rel = str(path.relative_to(root)).replace("\\", "/")
        if rel in EXCLUDE:
            continue
        if any(part in {".git", ".venv", "node_modules", "__pycache__", "examples"} for part in path.parts):
            continue
        yield path


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", default=".")
    parser.add_argument("--strict", action="store_true", help="fail on README / field notes / 13-15")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.path).resolve()
    results = [check_file(path, root) for path in sorted(iter_markdown(root))]
    strict_set = set(SHOP_WINDOW)
    failures = [r for r in results if r.hits and r.path in strict_set]

    if args.json:
        print(json.dumps([r.to_dict() for r in results if r.hits or r.dashes > 6], ensure_ascii=False, indent=2))
    else:
        total = 0
        for result in results:
            if not result.hits and result.dashes <= 6:
                continue
            total += len(result.hits)
            print(f"\n{result.path}  ({len(result.hits)} hit(s), {result.dashes} em dash(es))")
            for hit in result.hits[:12]:
                print(f"  L{hit['line']:<4} {hit['kind']:<18} {hit['text']}")
            if len(result.hits) > 12:
                print(f"  … {len(result.hits) - 12} more")
        print(f"\n{total} hit(s) across {len(results)} file(s)")
        if failures:
            print("shop-window files with hits:")
            for result in failures:
                print(f"  - {result.path}")
        else:
            print("shop-window files: clean")
    if args.strict and failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
