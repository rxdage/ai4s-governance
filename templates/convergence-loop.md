# 收敛环（模板）

> 没有 acceptance，循环就变成了聊天。
> 文件名：`LOOP-YYYYMMDD-<slug>.md`。

## 0. 目标

- objective：一句话，可判断“做完没有”。
- owner：谁对最终结果负责。
- 参与模型/工具：改的人、判的人（必须不同）。

## 1. 验收（acceptance）

> 必须是可执行的命令或检查清单，不是“读起来顺”“看起来对”。

```bash
# 示例
ai4s naming selftest
ai4s check <SR_DATA> --registry registry --library library
ai4s ingest verify --library library
```

- [ ] 检查 1：
- [ ] 检查 2：
- [ ] 检查 3：

## 2. 预算与停止条件

- max_rounds：3
- budget：____ token / ____ 分钟
- stop：
  - 全部 acceptance 通过；
  - 连续两轮没有可测改进；
  - 预算耗尽；
  - 出现不可逆风险。

## 3. 轮次日志

| 轮 | 改了什么 | 谁改的 | acceptance 结果 | 指标变化 | 花费 | 下一轮做什么 |
|---|---|---|---|---|---|---|
| 1 | | | | | | |
| 2 | | | | | | |
| 3 | | | | | | |

> 指标变化要写数字：通过几条、错几个、耗时多少。
> 只写“更好了”不算。

## 4. 结束

- 结果：通过 / 停止（原因）
- 最终 diff/产物：
- 人工 review：
  - [ ] diff 只包含目标改动
  - [ ] 没有绕过 acceptance
  - [ ] 回滚方式清楚
- 留痕：
  - [ ] 改动记录（evolution entry）
  - [ ] 成本记录
  - [ ] 如果失败，写清“卡在哪”

## 5. 三条纪律

1. 先写 acceptance，再让模型动手。
2. 改的人不能当裁判。
3. 连续两轮没有可测改进就停，换任务/换模型/找人。
