# 一页速查（Cheatsheet）

> 打印出来贴在工位上。完整规则见 [01-naming.md](01-naming.md) 与 [03-intake.md](03-intake.md)。

## 1. 五条原则

1. 机器不打开文件就能识别。
2. 人一眼看懂：谁 / 什么 / 什么条件 / 何时第几轮。
3. 先注册后使用；签的是内容，不是一个可以手改的标签。
4. 测出来的进 `data/`，算出来的进 `derived/`；后者必须带来源链 + 实名复核。
5. 只增不改：库内冻结；变更 = 同 T、RUN+1、整份重入；作废 = 留件 + 台账。

## 2. 四区

```
R0007_W0012_D0003__MEAS__BUF1_DAQ1__T202603041430_RUN0000.csv
└── 身份 ──┘        └类型┘ └─ 条件 ─┘ └──── 时序 ────┘
```

| 区 | 规则 |
|---|---|
| 1 | `R####_W####_D####`；4 位补零；`ALL` 只在 W/D；库级 `R0000_ALL_ALL` |
| 2 | 2–15 个纯大写字母；不含数字；必须已注册且已签 |
| 3 | `CLASS+数字`；不补零；同 class 一次；ASCII 排序；无条件写 `NA` 且独占 |
| 4 | `T` + 12 位 `YYYYMMDDHHMM` + `_RUN` + 4 位；两段必写；RUN 从 0000 起 |
| 全文 | `A-Z 0-9 _ .`；≤200 字节；库内唯一；不靠大小写区分 |

## 3. 角色

| 角色 | 一句话 |
|---|---|
| Owner | 产出数据、提名词条、跑自查、答 WARN |
| Steward | 签字、收库、抽查、放行、维护真值链（一个人） |
| Reviewer | 衍生数据 `reviewed_by`、模型/知识卡终审 |
| AI | 跑工具、产清单、改授权文件；不做决定 |

## 4. 一次交付（Owner）

```
命名 → ai4s check → ERROR=0 → 凭据 + 清单 → 传到 SR_DATA/ → 等回执
```

WARN 的动词是**答**，不是改。把本人原话填进 `_pending.csv` 的 `answer` 列。

## 5. 一次收库（Steward）

```
验凭据 → check → copy 空跑对账 → 人工抽查 3–5 个 → 备份 manifest
→ copy --apply → verify → 写台账 → 发回执
```

一次只收一个人；所有人的 `data` 收完再收 `derived`。

## 6. 衍生数据四道闸门

1. 有 `.meta.yaml`
2. `derived_from` 非空，且都在库里
3. `input_sha256` 与 manifest 一致
4. `reviewed_by` 是实名

## 7. 十二条红线（AI 永远不自动做）

签字 / `reviewed_by` / 去只读 / `copy --apply` / 人工抽查 / 改名 `--apply`（需点头）/
让文件消失 / “不入库”的决定 / 改已注册码 / 删除移动 / 台账放行人 / 发消息。

> 判据：错了还能改回去 → AI 可做；错了不可逆 → 只有人能做。

## 8. 节奏

| 时刻 | 做什么 |
|---|---|
| 每日 12:00 | 规则放行 + 回执 |
| 每日 12:30 | 字典侧人工审 |
| 周一/周五 08:00 | 巡检 |
| 周五 18:00 | 周总结（必须回看上一页） |
| 每月 | 看趋势 + 关掉一类死法 + 写“之后 0 例” |

## 9. 置信

| 级 | 含义 | 能做什么 |
|---|---|---|
| A | 数值实测 + 收敛 + 独立复核 | 可直接对外引用 |
| B | 真数值解，缺收敛或独立复核 | 趋势/量级 |
| C | 解析预测，未数值验证 | 预期/设计参考 |
| D | 估计/文献量级 | 只作数量级 |
| X | 已作废 | 只能解释“为什么错” |

## 10. 常用命令

```bash
ai4s naming selftest
ai4s naming check "<文件名>" --registry registry
ai4s audit <目录> --label "Lab A" --out audit_report.md
ai4s registry verify --registry registry
ai4s registry sign --registry registry --kind type --name MEAS --who "Li Ming" --date 2026-03-04 --apply
ai4s check <SR_DATA> --registry registry --library library
ai4s ingest copy <SR_DATA> --library library --registry registry
ai4s ingest copy <SR_DATA> --library library --registry registry --apply
ai4s ingest verify --library library
ai4s adoption --config lab.yaml
ai4s patrol --config lab.yaml
ai4s ledger check examples/ledger/deprecations.yaml
```

## 11. 卡住了

| 现象 | 先问 |
|---|---|
| `TYPE_UNKNOWN` / `CODE_UNKNOWN` | 这个码注册了吗？不要先改名 |
| `TYPE_NOT_APPROVED` | 等签字；不是你的错 |
| `SIGNATURE_STALE` | 签完又改了；重签，不要绕过 |
| `RUN_GAP` | 丢了 / 漏传 / 有意不交？ |
| `CONTENT_ID_MISMATCH` | 哪边是对的？本人拍板前一个字不改 |
| `撞名且内容不同` | 这是变更：T 不变、RUN+1 |
| `verify` 报被改 | 对去只读台账；无记录 = 事故 |
