# Security policy

## What to report

- A secret committed to the repository (token, key, password, private key).
- A way to make `selfcheck` or `ingest verify` report PASS when it should not.
- A path traversal / symlink issue in `ingest copy`.
- A webhook signature bypass in the Feishu adapter.

Please **do not** open a public issue for these. Use GitHub's private security
advisory, or contact the maintainer listed in the repository profile.

## Scope

This project is a local toolkit plus a reference adapter. It does not run a
hosted service. The most relevant assets are:

- the integrity of the library (`manifest.tsv`, sha256, read-only files);
- the signature ledger (`signatures.yaml`);
- the webhook endpoint if you deploy the Feishu adapter.

## Design assumptions

- The library is a normal directory. Read-only is a permission layer, not a
  transaction boundary; `verify` detects tampering after the fact.
- The bot never signs, copies or deletes. If a deployment gives it those
  permissions, that is a deployment bug, not a supported mode.
- The Feishu adapter handles plaintext callbacks and signature verification.
  Encrypted callbacks need an additional AES step; do not expose it publicly
  until you have added and tested that step.

## If a secret leaks

1. Rotate the secret first; deleting the commit is not enough.
2. Remove the secret from the working tree and, if needed, rewrite history.
3. Add a pattern to `scripts/scan_sensitive.py` so it cannot recur.
4. Record the incident in your team's ledger.

## Supported versions

Only the latest `main` is supported while the project is pre-1.0.
