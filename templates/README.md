# 模板索引

复制后改，不要直接改模板本身。

## 注册表

| 模板 | 用途 |
|---|---|
| [registry/type.yaml](registry/type.yaml) | 新增类型码 |
| [registry/class.yaml](registry/class.yaml) | 新增条件 class |
| [registry/code.yaml](registry/code.yaml) | 新增条件 code |
| [revision-order.md](revision-order.md) | 改自己码的记录性字段 |
| [change-request.md](change-request.md) | 改别人的码 |

## 交付

| 模板 | 用途 |
|---|---|
| [derived-sidecar.yaml](derived-sidecar.yaml) | 衍生数据的来源链 |
| [receipt-card.md](receipt-card.md) | 收库回执（由工具生成，模板只作对照） |

## 认知层

| 模板 | 用途 |
|---|---|
| [model-card.md](model-card.md) | 物理/计算模型卡（八段） |
| [kb-card.md](kb-card.md) | 知识库卡（指针，不复制本体） |
| [falsification-report.md](falsification-report.md) | 对抗复核报告 |
| [deprecation-entry.yaml](deprecation-entry.yaml) | 作废台账条目 |

## 运行

| 模板 | 用途 |
|---|---|
| [lab.yaml](lab.yaml) | 实验室配置 |
| [agent-prompt.md](agent-prompt.md) | 给 AI 的边界提示词 |
| [weekly-review.md](weekly-review.md) | 周总结（七节） |
| [evolution-entry.md](evolution-entry.md) | 架构改动记录（触发 / 代价 / 没解决） |
| [adoption-checkin.md](adoption-checkin.md) | 每两周的 adoption 检查 |
| [routing-policy.yaml](routing-policy.yaml) | 任务路由策略（档位而非供应商） |
| [convergence-loop.md](convergence-loop.md) | 收敛环：acceptance / 轮次 / 预算 |

## 使用原则

1. **模板是起点，不是合规证明。** 复制完要按你的团队改字段。
2. **不要留占位符。** `【…】`、`请替换成…`、`XX` 在交付前必须清掉。
3. **日期用 `YYYY-MM-DD`，布尔值不加引号。**
4. **签名/复核字段永远留空**，等人本人填。
