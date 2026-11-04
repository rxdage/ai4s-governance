# Walkthrough: 15 分钟跑完整个闭环

> 前置：Python 3.10+、PyYAML、本仓库。示例数据全部由脚本生成，不含真实数据。

## 0. 安装

```bash
cd ai4s-governance
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows
.venv\Scripts\activate
pip install -e .
```

## 1. 生成演示实验室

```bash
python examples/build_demo.py
```

它会生成：

```
examples/demo/
├── spec/filename-schema.yaml
├── registry/{types,classes,codes,classification,signatures}.yaml
├── library/{data,derived,index}/
├── workspaces/owner-a/{SR_DATA,REGISTRY,LIVEDOCS,PERSONAL}/
├── workspaces/steward/SR_DATA/
├── state/
└── lab.yaml
```

并自动完成：注册 → 签名 → 首次交付自查 PASS → 入库 → 生成衍生文件与 sidecar →
第二次自查 PASS → 再入库 → 全库 verify。输出类似：

```
dest: .../examples/demo
files: 5
warnings: 0
manifest_rows: 5
patrol_blocked: []
```

## 2. 看注册表

```bash
ai4s registry status --registry examples/demo/registry
```

```
[type]
  MEAS             APPROVED         signature=valid
  IMG              APPROVED         signature=valid
  SUMMARY          APPROVED         signature=valid
  CALIB            APPROVED         signature=valid
...
```

注意：条目本身写的是 `PROPOSED`，“APPROVED”是签名校验通过后的**有效状态**。
改一个字符，这里会变成 `SIGNATURE_STALE`。

## 3. 解析一个文件名

```bash
ai4s naming check "R0001_W0001_D0001__MEAS__BUF1_DAQ1__T202603041030_RUN0000.csv" \
  --registry examples/demo/registry
```

```
name      : R0001_W0001_D0001__MEAS__BUF1_DAQ1__T202603041030_RUN0000.csv
identity  : R0001 / W0001 / D0001
type      : MEAS  partition=data
conditions: BUF1_DAQ1
time      : 202603041030  RUN0000  ext=.csv
```

换个坏名字：

```bash
ai4s naming check "R0001_W0001_D0001__MEAS__NA_BUF1__T202603041030_RUN0000.csv" \
  --registry examples/demo/registry
```

```
  ERROR COND_NA_MIXED: NA 必须独占整个第三区，不能和别的码混写：'NA_BUF1'
```

## 4. 交付前自查

```bash
ai4s check examples/demo/workspaces/owner-a/SR_DATA \
  --registry examples/demo/registry \
  --library examples/demo/library
```

```
5 files, 0 ERROR, 0 WARN, answered 0/0
conclusion: PASS

snapshot: 9a7856ef6c0cef27
wrote: .../SR_DATA/_selfcheck_report.txt
```

产物：

| 文件 | 作用 |
|---|---|
| `_selfcheck_report.txt` | 逐条明细 |
| `_credential.txt` | **只有 PASS 才生成**；带注册表指纹 |
| `_delivery_list.csv` | 文件名 + 字节数，收库人逐条对 |
| `_pending.csv` | WARN 的逐条提问（示例为 0 条） |

> 程序判定 PASS，不是 AI 判定。删掉 `_credential.txt` 再跑一次，它会重新生成；
> 但一旦出现 ERROR，旧凭据会被自动删除。

## 5. 入库

先空跑：

```bash
ai4s ingest copy examples/demo/workspaces/owner-a/SR_DATA \
  --library examples/demo/library \
  --registry examples/demo/registry
```

```
batch 20261102-01  DRY-RUN
new=0 already=4 conflict=0 invalid=0
  already  data    R0001_W0001_D0001__MEAS__BUF1_DAQ1__T202603041030_RUN0000.csv
  ...
```

（demo 已经入过库，所以都是 `already`；空跑不写任何东西。）

校验：

```bash
ai4s ingest verify --library examples/demo/library
```

```
checked 5 rows: missing=0 modified=0 extra=0 bad_path=0
conclusion: OK
```

## 6. 巡检

```bash
ai4s patrol --config examples/demo/lab.yaml
```

```
patrol @ 2026-11-02T09:33:45+08:00  lab=demo-lab
people=2 files=5 errors=0 unanswered=0

[ok     ] Owner A      files=5    E=0   W=0   unanswered=0   cred=yes
[ok     ] Steward      files=0    E=0   W=0   unanswered=0   cred=no
```

## 7. 回执与放行

开一张回执：

```bash
ai4s bot receipt --config examples/demo/lab.yaml \
  --batch 20260305-01 --to owner-a
```

本人回：

```bash
ai4s bot handle --config examples/demo/lab.yaml --sender owner-a \
  "回执 20260305-01 1 已做"
```

```
已记：20260305-01 第 1 题 = 已做。下一轮巡检会按这个答复核。
```

乱答：

```bash
ai4s bot handle --config examples/demo/lab.yaml --sender owner-a \
  "回执 20260305-01 2 大概吧"
```

```
第 2 题只认：已做 / 未做；不认自由发挥
```

Steward 放行：

```bash
ai4s bot handle --config examples/demo/lab.yaml --sender steward \
  "放行 owner-a 依据 凭据 PASS，清单对上了"
```

```
已记放行：owner-a，依据「凭据 PASS，清单对上了」。
# 已记录放行意图；以下三条由 AI 代跑，署名与点头是你
cp .../manifest.tsv .../manifest.tsv.bak-...
ai4s ingest copy ... --apply
ai4s ingest verify --library ...
```

## 8. 看一个真实失败

```bash
ai4s ledger query examples/ledger/deprecations.yaml --contains "6.1"
```

```
DEP-IMG-001  [作废]  图像边缘场增强 6.1×，峰位在距边缘 16.6 µm 处
  -> 修复几何后膜内增强因子 β = 1.000，全窗口均匀；...
```

再看“什么还站得住”：

```bash
grep -A2 "caveats" examples/ledger/deprecations.yaml | head
```

## 9. 故意弄坏，确认能发现

```bash
# 把库内一个文件改成可写，再改内容
python - <<'PY'
from pathlib import Path
p = next(Path("examples/demo/library/data").rglob("*.csv"))
p.chmod(0o644)
p.write_text("tampered\n", encoding="utf-8")
PY

ai4s ingest verify --library examples/demo/library
```

```
checked 5 rows: missing=0 modified=1 extra=0 bad_path=0
  modified ... (size ... != ...)
conclusion: FAILED
```

## 10. 清理

```bash
python examples/build_demo.py --force   # 覆盖重建，会自动清掉只读文件
# 或手动删除：
rm -rf examples/demo                    # Windows: Remove-Item -Recurse -Force examples\demo
```

再跑一次 `python examples/build_demo.py` 就是全新的、哈希一致的 demo。

## 接下来

- 读 [01-naming.md](../docs/01-naming.md) 设计你自己的四区。
- 读 [04-roles-and-ai.md](../docs/04-roles-and-ai.md) 写你的 AI 边界提示词。
- 读 [08-adoption.md](../docs/08-adoption.md) 排 30/60/90 天。
