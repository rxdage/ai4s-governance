#!/usr/bin/env python
"""Vocabulary scan for a pile of existing filenames.

Use this before writing a naming spec, not after. It answers:

* which tokens dominate (and therefore which fields people actually use);
* which extensions exist;
* how many names already comply with a candidate schema;
* which error codes dominate (i.e. what migration will cost).

It does not decide anything. "Suspected" stays suspected.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ai4s_governance import naming  # noqa: E402

SPLIT_RE = re.compile(r"[_\-.+()\[\],;#&/\s]+")


def read_names(path: Path) -> List[str]:
    if not path.is_file():
        raise FileNotFoundError(path)
    out = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line:
            out.append(Path(line).name)
    return out


def scan(
    names: List[str],
    top: int = 30,
    registry: Optional[dict] = None,
    schema: Optional[dict] = None,
) -> Dict[str, object]:
    tokens: Counter = Counter()
    exts: Counter = Counter()
    errors: Counter = Counter()
    ok = 0
    parsed_ok = 0
    for name in names:
        stem, dot, ext = name.rpartition(".")
        if dot:
            exts["." + ext.lower()] += 1
        else:
            exts["(none)"] += 1
        for token in SPLIT_RE.split(name):
            if token:
                tokens[token.lower()] += 1
        if registry is not None or schema is not None:
            result = naming.parse(name, registry=registry, schema=schema)
            if result.ok:
                parsed_ok += 1
            for issue in result.errors:
                errors[issue.code] += 1
        if name.isascii():
            ok += 1
    return {
        "files": len(names),
        "ascii": ok,
        "parsed_ok": parsed_ok,
        "top_tokens": tokens.most_common(top),
        "extensions": exts.most_common(top),
        "error_codes": errors.most_common(top),
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("names", help="one filename per line")
    parser.add_argument("--top", type=int, default=30)
    parser.add_argument("--registry", default=None)
    parser.add_argument("--schema", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        names = read_names(Path(args.names))
    except FileNotFoundError:
        print(f"error: {args.names} not found", file=sys.stderr)
        return 2

    schema = naming.load_schema(args.schema) if args.schema else naming.load_schema()
    registry = None
    if args.registry:
        from ai4s_governance.registry import load_registry

        registry = load_registry(Path(args.registry), schema=schema).as_mapping()

    data = scan(names, top=args.top, registry=registry, schema=schema)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    print(f"files: {data['files']}  ascii: {data['ascii']}")
    if registry is not None:
        print(f"already compliant: {data['parsed_ok']} / {data['files']}")
        print("\n[top error codes]")
        for code, count in data["error_codes"]:
            print(f"  {count:>6}  {code}")
    print("\n[top tokens]")
    for token, count in data["top_tokens"]:
        print(f"  {count:>6}  {token}")
    print("\n[extensions]")
    for ext, count in data["extensions"]:
        print(f"  {count:>6}  {ext}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
