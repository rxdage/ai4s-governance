# AGENTS.md — instructions for AI agents working in this repository

You are working on **ai4s-governance**, a small toolkit plus a playbook. The
repository itself is a demonstration of the rules it describes. Do not break the
rules to make a check pass.

## Non-negotiable: human-facing prose

Everything a human will read — README, docs, field notes, release notes, posts,
emails, group announcements — must pass `docs/16-writing.md` and
`python scripts/humanize_check.py --path . --strict` before publishing.

AI drafts are input, not output. If a line is a deliberate exception (a quoted
example, a title), mark it with `<!-- humanize:ignore: reason -->`; do not disable
the checker.

## Your loop

```bash
python -m unittest discover -s tests -v
python examples/build_demo.py
ai4s registry verify --registry examples/demo/registry
ai4s check examples/demo/workspaces/owner-a/SR_DATA \
  --registry examples/demo/registry --library examples/demo/library --strict
ai4s ingest verify --library examples/demo/library
python scripts/scan_sensitive.py --path .
python scripts/humanize_check.py --path . --strict
```

All seven must pass before you claim a change works. Report the actual output, not
"should be fine".

## Hard boundaries

1. **Do not edit `src/ai4s_governance/selfcheck.py`, `spec/filename-schema.yaml`
   or `examples/build_demo.py` to make a failing example pass.** That bends the
   ruler. Fix the example or the rule, and add a test.
2. **Do not weaken a test.** If a test is wrong, explain why in the PR and add a
   test for the behaviour you believe is correct.
3. **No real data, names, IPs, paths, supplier names, or secrets.** Everything in
   `examples/` is synthetic. Use `Owner A`, `Demo Reviewer`, `example.org`.
4. **Do not add a dependency** beyond PyYAML without a decision entry.
5. **Do not translate the docs by machine and call it done.** If you translate,
   keep the Chinese original and mark the translation as a draft.

## Writing style

- Chinese docs: direct, concrete, table-friendly. Explain the failure mode before
  the rule. Include a counter-example.
- Every rule should answer: what does it prevent, what does it cost, and when
  should it be reconsidered.
- Do not add "best practice" prose that cannot be checked. If it matters, put it
  in the schema, a test, or a template.

## If you are operating a fork of this repo

Read `docs/04-roles-and-ai.md` and paste `templates/agent-prompt.md` into your
system prompt. The short version:

- You may run checks, produce rename plans, and edit yaml you were explicitly
  authorized to edit.
- You may not sign, fill `reviewed_by`, run `ingest copy --apply`, move/delete
  files, or answer a WARN on someone's behalf.
- PASS is decided by the program's exit code, not by your confidence.
- When unsure, stop and ask one or two concrete questions.
