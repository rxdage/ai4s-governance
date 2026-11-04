# Changelog

## v0.1.0 — 2026-03

First public, desensitized edition.

### Positioning

- Repositioned from "a data governance tool for agents" to **agent-native governance
  for AI4S R&D**: the agent is the main operator, not the beneficiary; the program
  decides PASS; humans keep every irreversible decision.
- Added a "When this is a fit" section and an explicit "what it won't do" boundary section
  (not a catalog, RAG memory, LIMS, BPM, or turnkey SaaS).
- Added `docs/github-listing.md` with the About text and topics.

### Added

- `docs/13-evolution.md`: fifteen architecture repairs, each with a trigger, a
  cost, an effect and what it did not solve.
- `docs/14-adoption.md`: five adoption milestones, a reconstructed curve, the
  adoption machinery, and the metrics to instrument (now `ai4s adoption`).
- `docs/15-agent-ops.md`: task routing by task type, convergence loops with
  acceptance tests, and cost per accepted change.
- `docs/16-writing.md`: the humanizer checklist for every human-facing text.
- `scripts/humanize_check.py`: a tripwire for common AI-writing tells; strict on
  the shop window (README, field notes, 13-15).
- `AGENTS.md`: a non-negotiable rule that human-facing prose passes the humanizer
  before publishing.
- `docs/field-notes/`: four publishable essays on the audit, the repair log,
  adoption speed, and model routing.
- `templates/evolution-entry.md`, `templates/adoption-checkin.md`,
  `templates/routing-policy.yaml`, `templates/convergence-loop.md`.
- `spec/filename-schema.yaml`: four-zone machine contract with configurable
  numbering, reserved words, derived-data gates and error-code vocabulary.
- `src/ai4s_governance/audit.py`: read-only lab data health check
  (`ai4s audit`), with a Markdown report and JSON output; `--names` audits a
  relative-path list without touching any file.
- `src/ai4s_governance/adoption.py`: M1–M5 adoption report from self-check
  logs, receipt tickets and registry proposals (`ai4s adoption`).
- `src/ai4s_governance/naming.py`: schema-driven parser with 7 positive and 16
  negative self-tests.
- `src/ai4s_governance/registry.py`: types/classes/codes with append-only,
  content-hash-bound signatures; stale-signature detection.
- `src/ai4s_governance/selfcheck.py`: delivery gate producing `_credential.txt`,
  `_delivery_list.csv`, `_pending.csv`; content-vs-filename cross-check;
  derived-data four gates.
- `src/ai4s_governance/ingest.py`: copy-only ingest, per-file manifest append,
  sha256 verification, read-only files, void ledger.
- `src/ai4s_governance/rename.py`: guarded all-or-nothing rename (five gates,
  original-name log).
- `src/ai4s_governance/patrol.py`: read-only per-person status snapshot.
- `src/ai4s_governance/bot.py` + `adapters/feishu.py`: adapter-agnostic receipt /
  release / reject / waiver / explain commands; Feishu reference transport.
- `src/ai4s_governance/ledger.py`: deprecation ledger validation and query.
- `examples/build_messy_lab.py`: 115 synthetic files covering the failure modes
  in the playbook; useful for audit demos and screenshots.
- `examples/build_demo.py`: a fully consistent demo lab (registry → signatures →
  delivery → ingest → derived → verify → patrol).
- `templates/`: registry entries, revision order, change request, sidecar,
  falsification report, deprecation entry, model card, KB card, receipt card,
  weekly review, agent prompt, evolution entry, adoption check-in, routing
  policy, convergence loop.
- `docs/00`–`docs/16`: the playbook in Chinese, plus English README.
- `scripts/scan_sensitive.py`: desensitization tripwire (IPs, paths, emails,
  keys, Office metadata, custom terms).
- `scripts/check_links.py`, `scripts/scan_names.py`: local-link check and a
  vocabulary scan for existing filenames.

### Deliberately not included

- A web dashboard (the bot's periodic report plus `manifest.tsv` answers the
  small-team question).
- Default encryption / classification enforcement (the interface is kept, the
  organizational key ceremony is not).
- Automatic rename / auto-fill of WARN / auto-sign (these are human decisions).
- Real data, real names, internal paths.
