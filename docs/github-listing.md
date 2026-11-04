# GitHub listing copy

> 复制粘贴用。仓库建好后在 GitHub 的 **About** 齿轮里填；或用 `gh repo edit`。
> 原则：**先说“为谁解决什么”，再说“怎么做到”**；不要用“AI 数据治理平台”这种会把预期带偏的词。

## Repository name

```
ai4s-governance
```

## Description (About, ≤350 chars)

```
Agent-native governance for AI4S (AI for Science) R&D: four-zone filenames, hash-bound registries, a single-source library, and a falsification ledger. Agents run the work; the program judges; people decide.
```

中文版（若 About 允许中文，或用于国内渠道）：

```
面向 AI4S（AI for Science）研发团队的 agent-native 治理层：四区命名、签名绑内容的注册表、一个只增不改的库、一本作废台账。agent 负责跑，程序负责判，人负责签字和放行。
```

## Topics (max 20)

```
ai4s
ai-for-science
data-governance
research-data-management
provenance
reproducibility
agents
llm
scientific-computing
laboratory
metadata
file-naming
audit
knowledge-management
falsification
research-software
python
```

> 不要加 `data-catalog`、`rag`、`vector-database`、`lims`：它们会把搜索流量带到错误的品类，
> 也会让访客用错误的标准评价这套东西。

## Social preview / 第一屏

```
Agent-native governance for AI4S (AI for Science)

Four-zone filenames. Signed registries. One library. A ledger of dead claims.
Agents run the work. The program judges. People decide.
```

## One-paragraph blurb (for newsletters, README mirrors)

```
A 5–50 person AI4S team has instruments, wet-lab data, simulations, and one agent per person — but no data engineer. This repo is a small, forkable kit for that team: four-zone filenames, a registry whose approvals are tied to content, one library that only grows, and a ledger for claims that turned out to be wrong. Agents do the running; the program decides PASS; people sign, spot-check and release.
```

## Release note (v0.1.0)

```
Initial public edition. Machine contract, parser, hash-bound registry signatures,
copy-only ingest with manifest/verify, derived-data provenance gates, guarded rename,
patrol, adapter-agnostic bot with Feishu reference adapter, demo lab, 15 templates,
a 13-part playbook, a one-page cheatsheet, and 38 tests.
```

## Suggested pinned issue

**Title:** What this repo is — and what it is not

**Body:**

```
This is a governance layer for AI4S labs where agents do most of the work. It is
not a data catalog, a RAG memory, a LIMS, or a turnkey SaaS.

It fits when:
- your agents can't find a file without opening it;
- nobody can prove who approved a code, or which version they approved;
- measured and computed results look the same on disk;
- a claim you killed two months ago is back in a slide deck.

It doesn't fit when the pain is catalog/lineage/PII, retrieval, or lab workflow.
README "When this is a fit" has the full list.
```

## How to apply

GitHub UI: repo → **About** (gear) → paste description → add topics → save.

`gh` CLI:

```bash
gh repo edit <owner>/ai4s-governance \
  --description "Agent-native governance for AI4S R&D: four-zone filenames, hash-bound registries, a single-source library, and a falsification ledger. Agents operate; the program judges; humans decide." \
  --add-topic ai4s \
  --add-topic ai-for-science \
  --add-topic data-governance \
  --add-topic research-data-management \
  --add-topic provenance \
  --add-topic reproducibility \
  --add-topic agents \
  --add-topic llm \
  --add-topic scientific-computing \
  --add-topic laboratory \
  --add-topic metadata \
  --add-topic file-naming \
  --add-topic audit \
  --add-topic knowledge-management \
  --add-topic falsification \
  --add-topic research-software \
  --add-topic python
```
