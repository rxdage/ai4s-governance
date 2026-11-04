# Overview (English)

> This is a one-page English entry to the playbook. The full documents are in
> Chinese under `docs/`; the code, schema, templates and examples are
> language-neutral. Translation PRs are welcome.

## The problem

Every lab has an afternoon like this: someone asks which file is the real one, and the room goes quiet. In a small AI4S team, four failures tend to show up together:

1. **The filename only means something to the person who made it.** Conditions live in folder names, versions are called `final_v2`, and an agent has to open every file to guess.
2. **The registry says `APPROVED`, but nobody can prove it.** The approval was typed into a field, not recorded as an event. One agent fills it with a job title; another edits the entry after signing.
3. **Measured and computed data sit in the same folder.** A fit result and the raw trace look the same on disk. Six months later, nobody can tell which is which.
4. **A dead claim comes back.** You falsified it in March. In June it is in a slide deck again, because the old deck never got the memo.

The common thread: the facts are not in a form a machine can check.

## Why now: the operator changed

Most governance assumes a patient person: reads the SOP, fills the metadata, remembers to unsign. Agents don't. They are fast, literal, confident, and will use whatever the tool leaves open — including "fixing" a warning by inventing a number. So the rules have to live at the tool boundary, and every irreversible action has to stay with a person. That is what *agent-native* means here: not a tool for agents, but governance built for a lab where agents do the work.

## When this is a fit

| If the pain is… | This repo | Use instead |
|---|---|---|
| Agents can't find a file without opening it | ✅ four-zone contract | — |
| Nobody can prove who approved which version | ✅ hash-bound signatures | — |
| "Is this number measured or computed?" | ✅ `data/` vs `derived/` + sidecars | — |
| A falsified claim keeps coming back | ✅ deprecation ledger + residue | — |
| A data catalog / lineage / PII platform | ❌ | DataHub, Collibra, OpenMetadata |
| A RAG memory / vector store for an LLM | ❌ | a retrieval layer; this is the layer underneath |
| A LIMS / ELN / workflow BPM | ❌ | integrate with them |
| A turnkey product with no semantic decisions | ❌ | this is a kit, not a SaaS |

The hard part isn't the parser. It's your registry and your history of dead claims. A vendor can copy the grammar; it can't copy the ontology or the ledger.

## Five principles

1. **Machine-readable without opening the file.** Identity, type, conditions and
   time are all in the filename; everything except the extension is uppercase.
2. **A human can read it at a glance.** Who / what / under what / when + run.
3. **Register before use.** Only registered and signed codes may appear in an
   archived filename; a signature binds to the entry's content hash.
4. **Measured and computed are separate.** Raw goes to `data/`, computed to
   `derived/`; the latter needs a provenance sidecar and a real reviewer.
5. **Append, never edit in place.** Library names are frozen; change = same `T`,
   `RUN + 1`, re-ingest; void = keep the file + ledger entry.

## The part most repos hide

This did not arrive as a finished architecture. It was repaired while five people used it: a false `APPROVED`, a staging folder that failed three times, a crash that lost manifest rows, 145 filename errors from an "AI-organized" delivery, a hand-made card that made a colleague's reply disappear. Each change has a trigger, a cost, and something it did not fix. The log is in [`docs/13-evolution.md`](../13-evolution.md); the adoption curve, and what we failed to measure, is in [`docs/14-adoption.md`](../14-adoption.md).

If you take one thing from this repo, take the order, not the final shape: scan before you specify, run one small batch before you automate, and decide who can decide before you pick tools.

## Four layers

| Layer | Artifact | Question |
|---|---|---|
| L1 contract | `spec/filename-schema.yaml` | what is a legal name |
| L2 registry | `registry/*.yaml` + `signatures.yaml` | what does a code mean, who approved it |
| L3 library | `library/` + `manifest.tsv` | how did it get here, has it changed |
| L4 knowledge | KB/model cards + `deprecations.yaml` | why should we believe a claim |

## The filename

```
R0007_W0012_D0003__MEAS__BUF1_DAQ1__T202603041430_RUN0000.csv
└── identity ─────┘ └type┘ └─ cond ──┘ └──── time ─────┘
```

- `R` batch/campaign, `W` sample/wafer, `D` unit/die/replicate.
- Zones separated by `__`; parts by `_`; four zones, none optional.
- `ALL` only in W/D; `R0000_ALL_ALL` for library-level files.
- Type: 2–15 uppercase letters. Condition: `CLASS + digits`, `NA` stands alone.
- Max 200 bytes; unique inside the library.

## The loop

```
owner names → selfcheck (ERROR=0 → credential) → copy into library
→ verify (recompute every hash) → steward spot-check + release
→ receipt card (frozen / rejected / open questions) → owner
```

The program decides PASS, not the agent. Warnings are questions for the owner;
an agent may not "fix" them. A delivery without a credential is not accepted.

## Roles

| Role | Does | Never does |
|---|---|---|
| Owner | names files, proposes codes, runs self-check, answers WARN | touches the library |
| Steward (one person) | signs, ingests, spot-checks, releases | edits someone else's files to "help" |
| Reviewer | `reviewed_by` for derived data, model/KB cards | answers WARN for an owner |
| Agent | runs tools, produces plans, edits authorized yaml | signs, ingests `--apply`, moves/deletes, answers WARN |

## Falsification

Before a claim enters `RESULTS.md`, a handoff page, a model card or the ledger, it
must survive a review whose default stance is **refute**:

- load-bearing claims get 3 independent perspectives, majority vote;
- supporting claims get 1 skeptic;
- 3 gap-finders look for unused analyses, untested assumptions and overclaims;
- output: `verification_raw.json`, `FALSIFIED.md`, `deprecations_draft.yaml`,
  a rewritten `RESULTS.md` with a "what you must not say" table;
- the ledger keeps `claim / verdict / correction / caveats / residue / scope`.
  `caveats` records what still stands; `residue` lists files where the old value
  still lives, so it can be swept.

## Adopt in 30/60/90 days

- **30:** scan existing names, write the contract, register 20 codes, run one
  real batch through the whole loop.
- **60:** fixed intake days, patrol, receipts, weekly review with a "last week"
  section.
- **90:** adversarial review of 3–5 load-bearing claims, a 10-entry ledger,
  confidence labels on model cards.

Start from one painful batch, not from a 40-page standard. The full argument,
including rejected alternatives and honest boundaries, is in
[`docs/00-overview.md`](../00-overview.md) and
[`docs/10-decisions.md`](../10-decisions.md).

## Honest boundaries

PASS means "no known trap was hit", not "the science is correct". A single
steward is a single point of failure. The library is a normal directory; read-only
is a permission layer, not a transaction boundary. There is no web dashboard by
design. If you need multi-writer transactions or >1000 files/day, redesign the
permission model before scaling.
