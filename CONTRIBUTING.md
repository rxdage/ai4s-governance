# Contributing

Thanks for taking a look. This repository is deliberately small; the most useful
contributions are the ones that **remove** complexity without losing a guarantee.

## Development

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows
.venv\Scripts\activate

pip install -e .
python -m unittest discover -s tests -v
python examples/build_demo.py
python scripts/scan_sensitive.py --path .
```

There is no formatter requirement, but keep the style of the surrounding code:
type hints, `from __future__ import annotations`, no external dependencies beyond
PyYAML.

## What to contribute

| Kind | Welcome? | Notes |
|---|---|---|
| Bug reports with a failing name/example | ✅ | Include the exact filename and expected error code |
| New transport adapter (Slack/Teams/Matrix/webhook) | ✅ | Keep `handle(sender, text)`; put it in `src/ai4s_governance/adapters/` |
| Translation of a doc | ✅ | Add `docs/xx-name.en.md`; do not delete the Chinese original |
| Case study from another AI4S domain | ✅ | Must be desensitized; use the checklist in `docs/12-publishing.md` |
| Simplification / rule deletion | ✅ | Explain which guarantee is preserved |
| New mandatory field | ⚠ | Needs a decision entry and a migration note |
| Real lab data | ❌ | Never. Use `examples/build_demo.py` to generate synthetic data |

## Changing the machine contract

1. Edit `spec/filename-schema.yaml`.
2. Run `ai4s naming selftest`; add positive/negative cases for any new rule.
3. Update `docs/01-naming.md` to match.
4. Add a decision to `docs/10-decisions.md`: context, options, cost, and **what
   would make you reconsider**.
5. Bump the schema semver. A major bump means parsers must refuse the old version.

## Pull request checklist

- [ ] `python -m unittest discover -s tests -v` passes.
- [ ] `python examples/build_demo.py` then the three `ai4s` commands pass.
- [ ] `python scripts/scan_sensitive.py --path .` returns 0.
- [ ] No real names, IPs, paths, supplier names, or secrets.
- [ ] Docs updated in the same PR as the code.
- [ ] Commit message says **why**. The what is in the diff.

## Style

- Chinese docs: direct, concrete, no marketing adjectives. Prefer a table or a
  counter-example over a paragraph of principles.
- Code: small functions, explicit error codes, no silent fallbacks.
- Comments explain *why*; the *what* should be readable from the code.

## Code of conduct

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).

## License

Contributions are accepted under MIT (code) and CC BY 4.0 (docs).
