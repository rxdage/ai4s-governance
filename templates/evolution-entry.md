# 架构改动记录（模板）

> 一次改动一条。写不出 `cost` 的，多半只是愿望。
> 文件名：`EVO-YYYYMMDD-<slug>.md`，放进你的 `docs/evolution/` 或 `LIVEDOCS/`。

```yaml
id: EVO-20260304-01
period: "Week 7"                 # 不要写真实日期也行；相对周更可复用
status: adopted                  # proposed | adopted | reverted
owner: Li Ming

trigger: >-
  一次跨网络复制 3000 个文件时崩溃。已落盘的文件没有 manifest 行；
  重跑判“已存在”又不再补行，这批文件永久缺失于账本。
symptom: >-
  verify 把它们全部报成“清单外文件”，而工具没有修复命令。

change: >-
  每落一个文件立刻写一行 manifest + fsync，不攒批。

cost: >-
  复制变慢（每文件一次 fsync）；代码多一个失败分支。

effect: >-
  之后两次中断重跑，manifest 行数与磁盘一致；verify 0 清单外。

unresolved: >-
  崩溃后仍需人工核对最后一批；没有自动回滚。

alternatives:
  - "复制完一次性写清单"            # 被否：崩溃会丢行
  - "先写清单再复制"                # 被否：清单会指向不存在的文件

decision_by: Steward
links: []
```

## 写法

- `trigger` 要具体到一次事故、一个数字，不写“为了提升效率”。
- `change` 一句话。写不清，说明还没想清。
- `cost` 必须写：时间、复杂度、人的耐心。
- `effect` 要可观察：0 清单外、0 复发、时间从 X 降到 Y。
- `unresolved` 比 `effect` 更重要；没有它，下一个人会以为问题全解决了。
- `alternatives` 写被否的方案和原因，防止下一个人再提一遍。
