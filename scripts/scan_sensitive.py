#!/usr/bin/env python
"""Scan a repository for common desensitization leaks before publishing.

This is a *tripwire*, not a guarantee. It catches the leaks that are easy to
miss when copying docs and code from a private repo:

* private IPs, UNC paths, home directories, NAS mounts;
* emails, phone numbers, API-key-looking strings, private-key headers;
* a user-supplied term list (real names, company, product, suppliers);
* Office document metadata (author / company) inside .docx/.xlsx/.pptx.

It does not read images or PDFs; do those by hand (see docs/12-publishing.md).

Usage:
    python scripts/scan_sensitive.py --terms /path/to/terms.txt
    python scripts/scan_sensitive.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Pattern, Tuple

TEXT_EXT = {
    ".md",
    ".txt",
    ".py",
    ".yaml",
    ".yml",
    ".json",
    ".toml",
    ".ini",
    ".cfg",
    ".csv",
    ".tsv",
    ".html",
    ".css",
    ".js",
    ".ts",
    ".sh",
    ".ps1",
    ".bat",
    ".tex",
    ".jsonl",
}
OFFICE_EXT = {".docx", ".xlsx", ".pptx"}
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", ".pytest_cache", "dist", "build"}

PATTERNS: List[Tuple[str, Pattern[str]]] = [
    ("private_ipv4", re.compile(r"\b(?:10\.\d{1,3}|192\.168\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3})\.\d{1,3}\b")),
    ("ipv4", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("unc_path", re.compile(r"\\\\[A-Za-z0-9_.-]+\\[A-Za-z0-9_.$-]+")),
    ("smb_url", re.compile(r"smb://[^\s)]+", re.I)),
    ("posix_home", re.compile(r"/(?:home|Users)/[A-Za-z0-9_.-]+/")),
    ("nas_mount", re.compile(r"/mnt/(?:nas|disk\d+)/[^\s)`]*", re.I)),
    ("windows_user_path", re.compile(r"[A-Za-z]:\\Users\\[A-Za-z0-9_.-]+", re.I)),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("cn_mobile", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("api_key", re.compile(r"\b(?:sk|pk|ghp|gho|ghs|xox[baprs]|AKIA)[-_A-Za-z0-9]{16,}\b")),
    ("bearer_token", re.compile(r"Bearer\s+[A-Za-z0-9._~+/-]{20,}")),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("password_assignment", re.compile(r"(?i)\b(?:password|passwd|secret|token)\s*[:=]\s*(?:['\"][A-Za-z0-9._~+/-]{16,}['\"]|[A-Za-z0-9+/=_-]{24,})")),
]

ALLOW_LINE_MARKERS = ("scan:allow", "scan: allow")

# Matches that are usually harmless in documentation and examples.
ALLOW = [
    re.compile(r"\b127\.0\.0\.1\b"),
    re.compile(r"\b0\.0\.0\.0\b"),
    re.compile(r"\b(?:10|192)\.0\.0\.\d{1,3}\b"),  # documentation example ranges
    re.compile(r"@example\.(?:com|org)"),
    re.compile(r"@github\.com\b"),
]


@dataclass
class Hit:
    path: str
    line: int
    kind: str
    preview: str

    def to_dict(self) -> Dict[str, str]:
        return {"path": self.path, "line": self.line, "kind": self.kind, "preview": self.preview}


def _redact(text: str, limit: int = 80) -> str:
    text = " ".join(text.strip().split())
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text


def _allowed(text: str) -> bool:
    return any(rx.search(text) for rx in ALLOW)


def term_pattern(term: str) -> Pattern[str]:
    term = term.strip()
    if not term:
        raise ValueError("empty term")
    if re.search(r"[\u4e00-\u9fff]", term):
        return re.compile(re.escape(term))
    return re.compile(r"(?<![A-Za-z0-9_-])" + re.escape(term) + r"(?![A-Za-z0-9_-])", re.I)


def load_terms(path: Optional[Path]) -> List[Tuple[str, Pattern[str]]]:
    if not path:
        return []
    out = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        out.append((line, term_pattern(line)))
    return out


def iter_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def scan_text(path: Path, root: Path, terms: List[Tuple[str, Pattern[str]]]) -> List[Hit]:
    hits: List[Hit] = []
    rel = str(path.relative_to(root))
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return hits
    for lineno, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        if any(marker in line.lower() for marker in ALLOW_LINE_MARKERS):
            continue
        for kind, rx in PATTERNS:
            for match in rx.finditer(line):
                if _allowed(match.group(0)):
                    continue
                hits.append(Hit(rel, lineno, kind, _redact(line)))
                break
        for term, rx in terms:
            if rx.search(line):
                hits.append(Hit(rel, lineno, f"term:{term}", _redact(line)))
    return hits


def scan_office(path: Path, root: Path, terms: List[Tuple[str, Pattern[str]]]) -> List[Hit]:
    hits: List[Hit] = []
    rel = str(path.relative_to(root))
    try:
        with zipfile.ZipFile(path) as zf:
            for name in ("docProps/core.xml", "docProps/app.xml"):
                if name not in zf.namelist():
                    continue
                xml = zf.read(name).decode("utf-8", errors="ignore")
                for tag in ("dc:creator", "cp:lastModifiedBy", "Company", "Manager"):
                    for m in re.finditer(rf"<{tag}[^>]*>([^<]+)</{tag}>", xml):
                        value = m.group(1).strip()
                        if not value:
                            continue
                        hits.append(Hit(rel, 0, f"office_meta:{tag}", _redact(value)))
                        for term, rx in terms:
                            if rx.search(value):
                                hits.append(Hit(rel, 0, f"term:{term}", _redact(value)))
    except (zipfile.BadZipFile, OSError):
        return hits
    return hits


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", default=".", help="repository root")
    parser.add_argument("--terms", default=None, help="one sensitive term per line")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--exclude",
        action="append",
        default=["scripts/scan_sensitive.py", "examples/demo"],
        help="relative path or prefix to skip (repeatable)",
    )
    args = parser.parse_args(argv)

    root = Path(args.path).resolve()
    terms = load_terms(Path(args.terms) if args.terms else None)
    excludes = [e.replace("\\", "/").strip("/") for e in args.exclude]
    hits: List[Hit] = []

    for path in iter_files(root):
        rel = str(path.relative_to(root)).replace("\\", "/")
        if any(rel == e or rel.startswith(e + "/") for e in excludes):
            continue
        if path.name == "scan_sensitive.py":
            continue
        suffix = path.suffix.lower()
        if suffix in TEXT_EXT:
            hits.extend(scan_text(path, root, terms))
        elif suffix in OFFICE_EXT:
            hits.extend(scan_office(path, root, terms))

    if args.json:
        print(json.dumps([h.to_dict() for h in hits], ensure_ascii=False, indent=2))
    else:
        for hit in hits:
            print(f"{hit.path}:{hit.line}: [{hit.kind}] {hit.preview}")
        print(f"\n{len(hits)} hit(s) in {root}")
        if hits:
            print("review each hit; redact, replace with a placeholder, or allowlist it explicitly.")
    return 0 if not hits else 1


if __name__ == "__main__":
    raise SystemExit(main())
