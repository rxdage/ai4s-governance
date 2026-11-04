# 五个人多久才开始用？我们当时没量

**English title:** How fast do five scientists adopt governance? We didn't measure it.
**English hook:** Adoption is not "read the doc". It is the first PASS, the first self-initiated check, the first receipt. We learned that the hard way, and then built the instrument we should have had on day one.

---

第一版自查包发出去那天，一位同事跑完，发回来 145 个文件名语法错、192 个用了没注册的码。

他并不懒。是他的 AI 告诉他“应该能过了”，他就信了。

我们一开始以为 adoption 是大家读过文档。后来发现，分界线是第一次拿到 PASS。

后来我们把 adoption 拆成五件事：

- **M1**：第一次拿到 PASS 凭据。
- **M2**：第二天、没人催，又跑了一次。
- **M3**：第一次按格式回执。
- **M4**：第一次在 `REGISTRY/` 提一个新码。
- **M5**：第一次向别人解释一条规则。

M1 之前，他还在旁边看。M2 之后，这件事才变成他自己的习惯。

## 一条重建的曲线

我们当时没有把 adoption 做成指标。下面是后来从交付记录、回执、周总结里重建的：

| 时间 | 发生了什么 | 卡在哪 |
|---|---|---|
| 第 1 周 | 第一位同事跑出第一个 PASS | 145 个语法错、192 个未注册码；AI 说“应该能过” |
| 第 2–3 周 | 第二、三位开始用，主要靠人陪跑 | “我的 AI 说没问题”；不敢点 `--apply` |
| 第 4 周 | 第一批回执；大约 3/5 有 PASS | 凭据快照对不上；包换得太勤 |
| 第 6 周 | 第四位加入；周总结固定 | 周总结变成流水账 |
| 第 8 周 | 第一次没人催的自查 | 仍有人把 WARN 当“改掉就好” |
| 第 4 个月 | 新人用“包 + AI 提示词”入职，约 1 天出第一个 PASS | 老人仍用旧习惯处理例外 |

除了 145/192、162 条签字、0 复发这些有记录的数字，其他是重建的。这是最后悔的一件事：没有从第一天就量。

## 什么加速了 adoption

我们没做培训课。起作用的是四样东西：

1. **一条命令**：`ai4s check <我的目录>`。不是“先读 40 页规范”。
2. **一句人话**：报错写“原因 / 该做”，不是只给错误码。
3. **一个人**：出问题能问谁。第一位 champion 比任何文档都重要。
4. **一张绿卡**：没事也发卡。这样“没收到卡”本身就是一个信号。

还有几个“把决定变少”的设计：每人四个夹子（SR_DATA / REGISTRY / LIVEDOCS / PERSONAL）、明令“不要整理文件夹”、变更只有一条路（T 不变、RUN+1）。每多一条规则，就多一个决定。我们后来只保留必须的决定。

## 什么拖慢了 adoption

- **145 个语法错、192 个未注册码**：这不能怪人笨。工具报错没有“该做”，人只能猜。
- **AI 的自信**：“应该能过”让本人以为不用跑。
- **手拼卡没有底稿**：同事照卡回了，机器拒收，还怪他抄错号。
- **WARN 被当成“改掉就好”**：一改就是编数据，越帮越忙。
- **包换得太勤**：凭据快照对不上，收库打回，信任消耗。
- **单点 Steward**：一个人扛全部复杂度，他一忙，全员停。

## 现在怎么量

`ai4s check` 每次可以追加一行日志；`ai4s adoption` 从日志、回执、提案里算 M1–M4，外加 time-to-first-PASS 和 rounds：

```bash
ai4s check <SR_DATA> --registry registry --library library \
  --log state/selfcheck_runs.jsonl --person owner-a

ai4s adoption --config lab.yaml --out state/adoption_report.md
```

M5 只能人工观察。

如果只能留一个 adoption 指标，我留 **time to first PASS**。培训覆盖率、文档阅读量都不如它。一个人第一次看到“程序说 PASS”，比任何动员都有效。

我们第一次跑真实 `SR_DATA` 的体检：931 个数据文件，100% 可解析；同一周跑一份旧测试包，60 个文件，0%。这不是“所有人都改完了”，但它说明：改完的那部分，机器真的能读懂。

完整版：[docs/14-adoption.md](../14-adoption.md)。想先看看自己团队的起点：`ai4s audit <目录>`。
