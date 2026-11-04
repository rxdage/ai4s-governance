# spec/ · 机器契约

| 文件 | 是什么 |
|---|---|
| [`filename-schema.yaml`](filename-schema.yaml) | ★ 唯一机器真值：四区文法、语义、错误码、入库契约 |
| [`schemas/derived-sidecar.schema.json`](schemas/derived-sidecar.schema.json) | 衍生 sidecar 的 JSON Schema（可选校验） |
| [`schemas/deprecation.schema.json`](schemas/deprecation.schema.json) | 作废台账条目的 JSON Schema（可选校验） |
| [`schemas/model-card.schema.json`](schemas/model-card.schema.json) | 模型卡 front-matter 的 JSON Schema（可选校验） |

## 为什么是 YAML，不是 Markdown

- 解析器从 YAML 读正则、字符集、上限、编号起点、保留字、错误码；
- 改规则只改一处，`ai4s naming selftest` 会立刻告诉你有没有破坏正反例；
- 文档（`docs/01-naming.md`）只是人类解释，冲突时 YAML 赢。

## 改契约的流程

1. 改 `filename-schema.yaml`。
2. 跑 `ai4s naming selftest`；改了解析器就补正反例。
3. 改 `docs/01-naming.md` 到一致。
4. 在 `docs/10-decisions.md` 写一条决策：背景、选项、代价、什么条件下重新考虑。
5. 升 `filename_schema` 的 semver；主版本变了，解析器必须拒绝旧版（防止半迁移）。

## 版本策略

- `1.0.0` 当前。
- 加一个可选字段/错误码 → minor。
- 改分区文法、字符集、必填字段 → major。
- 只改注释/文档 → 不动版本。
