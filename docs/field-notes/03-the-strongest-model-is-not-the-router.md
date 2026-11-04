# 为什么用最强模型改流程还是错，还贵

**English title:** The strongest model is not the best router
**English hook:** We used the strongest model for every edit. It was expensive, slow, and still wrong. The fix was not a stronger model; it was task routing and a stop condition.

---

有一段时间，我们的默认做法是：所有事都用最强的模型。

改一个流程文档，用它；重写一段脚本，用它；跑一次巡检，也用它。结果是：贵、慢，还是错。

最典型的一次：一段流程文档改了五轮。每一轮都“更完整”，但没人删内容；最后文档更长了，新同事还是问同一个问题。验收标准是“读起来顺”，不是“新同事能照着做”。

后来我们把问题拆成两个。

## 问题一：任务没有分层

有些活不值得用最强模型。

| 任务 | 例子 | 路由 | 为什么 |
|---|---|---|---|
| 机械编辑 | 批量改名、格式统一、字段重排 | 便宜/快的 harness | 可验证、可回滚 |
| 代码/配置 | 脚本、CI、schema | 中等模型 + 测试 | 有测试可判 |
| 判断/设计 | 架构、语义、冲突裁决 | 最强模型 | 需要上下文和推理 |
| 对抗复核 | 证伪、找漏洞 | **与作者不同的模型/视角** | 独立性 |
| 例行检查 | 巡检、对账、报告 | 小模型/规则 | 确定性高 |
| 不可逆动作 | 签字、发布、删除 | **不路由** | 错了不可逆 |

我们试过把机械改动从最贵的模型上挪到一个更便宜的 harness，把判断留给强模型。同一个流程，错误少了，钱也少了。

便宜模型不一定更好。关键是别把机械活交给最贵的模型。

## 问题二：循环没有停止条件

“再改一版看看”通常不会收敛。收敛环需要五个东西：

```yaml
objective: 一句话说清要什么
acceptance: 可执行的检查，不是“看起来对”
max_rounds: 3
budget: token / 时间上限
stop: 通过 / 连续两轮无改进 / 预算耗尽
```

把 acceptance 改清楚之后，很快就收敛了。模型没变强。是“过”的定义变清楚了：

1. 新同事能在 10 分钟内跑完 demo；
2. 三个命令的输出与文档一致；
3. 一个没看过原文的人能复述“先做什么、后做什么”。

**没有 acceptance，循环就变成了聊天；你永远不知道什么时候该停。**

## 成本：不要只看 token 单价

一个便宜的模型如果 5 轮才过，可能比强模型 1 轮更贵。要看：

- **cost per accepted change**：总花费 / 被接受的改动数；
- **rounds to converge**：几轮通过；
- **rework rate**：接受后又被回滚的比例；
- **human minutes**：人花在 review/裁决上的时间。

token 不是最贵的。最贵的是人坐在那里等和改。

## 什么不要路由

- 签字、发布、删除、发消息：没有“重试”。
- 科学判断：模型可以提假设，不能背书。
- 对抗复核：让作者模型复核自己，等于没复核。
- 组织/人际判断：模型没有上下文。

## 不要把品牌写进流程

模型版本一个季度就变。今天“谁比谁好”，下个季度可能反过来。

所以公开版只写档位：`cheap-fast`、`mid`、`frontier`、`not-routed`。具体哪家模型，放在配置里，不写进制度。可复用、可卖的是**路由策略 + 验收标准 + 成本指标**，不是某一家模型。

完整版：[docs/15-agent-ops.md](../15-agent-ops.md)。模板：[routing-policy.yaml](../../templates/routing-policy.yaml)、[convergence-loop.md](../../templates/convergence-loop.md)。
