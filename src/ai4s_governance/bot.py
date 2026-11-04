"""Adapter-agnostic bot core.

The bot is a *small* part of the system: it turns a human sentence into a
recorded decision (receipt, release, reject, waiver) and answers "what does this
word mean". It never signs, never copies files, never edits a registry.

Transport is pluggable; see ``adapters/feishu.py`` for the reference adapter.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

import yaml

from .patrol import load_lab, resolve

GLOSSARY = {
    "四区制": "文件名由身份__类型__条件__时序四段组成，缺一区即非法。",
    "RUN": "同一芯片、同一类型、同一条件组下的第几次执行，从 0000 起。",
    "ALL": "只允许出现在 W、D 两个槽位；W=ALL 时 D 必须也是 ALL。",
    "R0000": "库级文件专用批次号，永不用于真实批次。",
    "PROPOSED": "已提案、未签字。不能出现在归档文件名里。",
    "derived": "算出来的数据（拟合/汇总/统计/AI 分析），必须配 sidecar 并实名复核。",
    "作废": "原地留库、只读、进作废清单；不移动、不删除。",
    "回执": "收库后给交付人的卡：冻了什么、拒了什么、还剩哪几题要本人答。",
    "豁免": "让某条待办暂时不算数的书面记录，必须写到期日和理由。",
    "凭据": "自查 PASS 后程序生成的 _credential.txt；判定 PASS 的是程序，不是 AI。",
}


@dataclass
class Reply:
    text: str
    recorded: bool = False
    action: str = ""
    data: Dict[str, Any] = field(default_factory=dict)


class BotCore:
    def __init__(self, config_path: Path, dry_run: Optional[bool] = None):
        self.config_path = Path(config_path).resolve()
        self.base = self.config_path.parent
        cfg = load_lab(self.config_path)
        self.cfg = cfg
        bot_cfg = cfg.get("bot", {}) or {}
        self.state_dir = resolve(self.base, str(bot_cfg.get("state_dir", "state")))
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.dry_run = bool(bot_cfg.get("dry_run", True)) if dry_run is None else dry_run
        self.people = {str(p.get("id")): p for p in cfg.get("people", [])}
        self.steward = str(bot_cfg.get("steward", "steward"))
        self.library = resolve(self.base, cfg.get("paths", {}).get("library", "library"))
        self.receipts_path = self.state_dir / "receipts.json"
        self.tickets_path = self.state_dir / "tickets.jsonl"
        self.waivers_path = self.state_dir / "waivers.yaml"
        self.glossary = dict(GLOSSARY)
        glossary_file = self.base / "glossary.yaml"
        if glossary_file.is_file():
            with glossary_file.open("r", encoding="utf-8") as fh:
                extra = yaml.safe_load(fh) or {}
            if isinstance(extra, dict):
                self.glossary.update({str(k): str(v) for k, v in extra.items()})

    # -- state ------------------------------------------------------------
    def _load_json(self, path: Path, default: Any) -> Any:
        if not path.is_file():
            return default
        try:
            with path.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            return default

    def _save_json(self, path: Path, data: Any) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def _append_ticket(self, record: Mapping[str, Any]) -> None:
        record = dict(record)
        record.setdefault("at", datetime.now().astimezone().isoformat(timespec="seconds"))
        with self.tickets_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    def tickets(self) -> List[Dict[str, Any]]:
        if not self.tickets_path.is_file():
            return []
        out = []
        for line in self.tickets_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    def waivers(self) -> List[Dict[str, Any]]:
        if not self.waivers_path.is_file():
            return []
        with self.waivers_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return list(data.get("waivers", []))

    def _save_waivers(self, rows: List[Dict[str, Any]]) -> None:
        self.waivers_path.write_text(
            yaml.safe_dump({"waivers": rows}, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

    # -- receipts ---------------------------------------------------------
    def open_receipt(
        self,
        batch: str,
        questions: Iterable[Mapping[str, Any]],
        recipients: Iterable[str],
    ) -> Dict[str, Any]:
        data = self._load_json(self.receipts_path, {"batches": {}})
        qs = []
        for q in questions:
            options = list(q.get("options") or ["已做", "未做"])
            qs.append(
                {
                    "id": str(q["id"]),
                    "text": str(q.get("text", "")),
                    "options": [str(o) for o in options],
                }
            )
        data.setdefault("batches", {})[batch] = {
            "batch": batch,
            "sent_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "recipients": [str(r) for r in recipients],
            "questions": qs,
        }
        self._save_json(self.receipts_path, data)
        return data["batches"][batch]

    def render_receipt(self, batch: str) -> str:
        data = self._load_json(self.receipts_path, {"batches": {}})
        rec = data.get("batches", {}).get(batch)
        if not rec:
            return f"没有这个批次：{batch}"
        lines = [f"回执卡 · 批次 {batch} · 群发 {rec['sent_at']}", ""]
        lines.append("[R] 只有本人能答   [Y] AI 可代跑但需点头")
        for q in rec["questions"]:
            lines.append(f"{q['id']}. {q['text']}  选项：{' / '.join(q['options'])}")
        lines.append("")
        lines.append(f"回复格式：回执 {batch} <题号> <选项>")
        return "\n".join(lines)

    # -- main dispatcher --------------------------------------------------
    def handle(self, sender: str, text: str) -> Reply:
        sender = str(sender)
        text = (text or "").strip()
        if sender not in self.people:
            return Reply("你不在名单里，先让管理员把你加进 lab.yaml 的 people。")

        if text.startswith(("回执", "receipt")):
            return self._handle_receipt(sender, text)
        m = re.match(r"^放行\s+(\S+)\s+依据\s+(.+)$", text, re.S)
        if m:
            return self._handle_release(sender, m.group(1), m.group(2))
        m = re.match(r"^拒收\s+(\S+)\s+(.+)$", text, re.S)
        if m:
            return self._handle_reject(sender, m.group(1), m.group(2))
        m = re.match(r"^豁免\s+(\S+)\s+(\S+)\s+到\s+(\d{4}-\d{2}-\d{2})\s+(.+)$", text, re.S)
        if m:
            return self._handle_waiver(sender, m.group(1), m.group(2), m.group(3), m.group(4))
        m = re.match(r"^解释\s+(.+)$", text, re.S)
        if m:
            term = m.group(1).strip()
            return Reply(self.glossary.get(term, f"词表里没有 {term!r}。"))
        m = re.match(r"^状态(?:\s+(\S+))?$", text)
        if m:
            return Reply(self._status(sender, m.group(1)))
        return Reply("没听懂。可用：回执 / 放行 / 拒收 / 豁免 / 解释 / 状态。")

    # -- handlers ---------------------------------------------------------
    def _handle_receipt(self, sender: str, text: str) -> Reply:
        parts = text.split()
        if len(parts) < 4:
            return Reply("格式：回执 <批次号> <题号> <选项>，例如 回执 20260304-01 1 已做")
        target = sender
        if (
            sender == self.steward
            and len(parts) >= 5
            and parts[0] in {"回执", "receipt"}
            and parts[1] in self.people
        ):
            # Steward filing on behalf: 回执 <person> <batch> <qid> <answer>
            target = parts[1]
            batch, qid, answer = parts[2], parts[3], " ".join(parts[4:])
        else:
            batch, qid, answer = parts[1], parts[2], " ".join(parts[3:])
        data = self._load_json(self.receipts_path, {"batches": {}})
        rec = data.get("batches", {}).get(batch)
        if not rec:
            return Reply(f"批次 {batch} 不存在，或这张卡还没群发（没底稿的卡机器不认）。")
        if target not in rec["recipients"]:
            return Reply(f"这张回执不是发给 {target} 的。")
        if sender != target and sender != self.steward:
            return Reply("这张回执不是发给你的；代填只有管理员能做。")
        question = next((q for q in rec["questions"] if q["id"] == qid), None)
        if question is None:
            return Reply(f"第 {qid} 题不存在。这张卡只有：" + ", ".join(q["id"] for q in rec["questions"]))
        if answer not in question["options"]:
            return Reply(
                f"第 {qid} 题只认：{' / '.join(question['options'])}；"
                "不认自由发挥（原来的事故就是选项后多写一句，整条被拒）。"
            )
        self._append_ticket(
            {
                "type": "receipt",
                "person": target,
                "batch": batch,
                "qid": qid,
                "answer": answer,
                "filed_by": sender,
                "raw": text,
            }
        )
        who = "" if target == sender else f"（代 {target} 填）"
        return Reply(
            f"已记{who}：{batch} 第 {qid} 题 = {answer}。下一轮巡检会按这个答复核。",
            recorded=True,
            action="receipt",
        )

    def _steward_only(self, sender: str) -> Optional[Reply]:
        if sender != self.steward:
            return Reply("只有管理员能做这个动作。")
        return None

    def _handle_release(self, sender: str, person: str, reason: str) -> Reply:
        denied = self._steward_only(sender)
        if denied:
            return denied
        if person not in self.people:
            return Reply(f"名单里没有 {person}")
        self._append_ticket(
            {"type": "release", "person": person, "reason": reason, "by": sender}
        )
        ws = resolve(self.base, str(self.people[person].get("workspace", "")))
        commands = (
            f"# 已记录放行意图；以下三条由 AI 代跑，署名与点头是你\n"
            f"cp {self.library}/index/manifest.tsv "
            f"{self.library}/index/manifest.tsv.bak-$(date +%Y%m%d-%H%M)\n"
            f"ai4s ingest copy {ws / 'SR_DATA'} --library {self.library} "
            f"--registry {self.base / 'registry'} --apply\n"
            f"ai4s ingest verify --library {self.library}"
        )
        return Reply(
            f"已记放行：{person}，依据「{reason}」。\n{commands}",
            recorded=True,
            action="release",
        )

    def _handle_reject(self, sender: str, person: str, reason: str) -> Reply:
        denied = self._steward_only(sender)
        if denied:
            return denied
        self._append_ticket(
            {"type": "reject", "person": person, "reason": reason, "by": sender}
        )
        return Reply(f"已记拒收：{person}，原因「{reason}」。", recorded=True, action="reject")

    def _handle_waiver(
        self, sender: str, person: str, code: str, until: str, reason: str
    ) -> Reply:
        denied = self._steward_only(sender)
        if denied:
            return denied
        try:
            datetime.strptime(until, "%Y-%m-%d")
        except ValueError:
            return Reply("到期日必须是 YYYY-MM-DD")
        rows = self.waivers()
        rows.append(
            {
                "person": person,
                "code": code,
                "until": until,
                "reason": reason,
                "by": sender,
                "at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "active": True,
            }
        )
        self._save_waivers(rows)
        return Reply(
            f"已豁免：{person} 的 {code} 到 {until}，理由「{reason}」。",
            recorded=True,
            action="waiver",
        )

    def _status(self, sender: str, who: Optional[str]) -> str:
        target = who or sender
        if target not in self.people:
            return f"名单里没有 {target}"
        data = self._load_json(self.receipts_path, {"batches": {}})
        tickets = [t for t in self.tickets() if t.get("person") == target]
        answered = {(t.get("batch"), t.get("qid")): t.get("answer") for t in tickets if t.get("type") == "receipt"}
        lines = [f"状态 · {self.people[target].get('name', target)}"]
        open_count = 0
        for batch, rec in sorted(data.get("batches", {}).items()):
            if target not in rec.get("recipients", []) and target != self.steward:
                continue
            for q in rec.get("questions", []):
                key = (batch, q["id"])
                if key in answered:
                    lines.append(f"  [done] {batch} 第{q['id']}题：{answered[key]}")
                else:
                    open_count += 1
                    lines.append(f"  [open] {batch} 第{q['id']}题：未回（按未做算）")
        if open_count == 0:
            lines.append("  没有开着的题。")
        waivers = [w for w in self.waivers() if w.get("person") == target]
        for w in waivers:
            lines.append(f"  [waive] {w['code']} 到 {w['until']}：{w['reason']}")
        return "\n".join(lines)

    # -- AI-facing helper -------------------------------------------------
    def ai_brief(self) -> str:
        """A compact boundary statement to paste into an agent prompt."""
        return (
            "你在这个实验室里的边界：\n"
            "1. 你可以跑 selfcheck、产改名清单、改你自己被明确授权的 yaml。\n"
            "2. 你不能签字、不能填 reviewed_by、不能跑入库 --apply、不能删/移/改名以外的任何文件。\n"
            "3. 判定 PASS 的是程序，不是你的判断；以 _credential.txt 为准。\n"
            "4. WARN 的动词是「答」，不是「改」；你没有资格替本人回答。\n"
            "5. 拿不准就问，不要猜；编一个看起来合理的数会污染所有下游结论。\n"
        )


def load_bot(config_path: Path, dry_run: Optional[bool] = None) -> BotCore:
    return BotCore(config_path, dry_run=dry_run)
