"""synthlabel —— 给合成数据标注它的生成方式与可信度。

设计原则：
1. **合成数据也得有出生证明**。标签跟着数据走，将来发现问题时能一路查回去。
2. **筛选依据必须记下来**。筛掉什么，等于决定了留下什么。
3. **不确定度不许伪装成确定**。机器标出来的置信度就是机器标出来的。

仅依赖 Python 标准库。

用法:
    python synthlabel.py --help
    python synthlabel.py --data synth.jsonl --label-out labeled.jsonl
    python synthlabel.py --data synth.jsonl --audit
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter

# ---------------------------------------------------------------------------
# 标签结构
# ---------------------------------------------------------------------------

LABEL_FIELDS = ("generated_by", "generated_at", "filter_criteria",
                "uncertainty", "source_ref", "review_status")

REVIEW_STATUS = ("unreviewed", "reviewed_ok", "reviewed_rejected", "needs_human")

# 生成方式：按名字猜模型族
GEN_PATTERNS = [
    ("gpt", re.compile(r"\bgpt[-_ ]?\d", re.I)),
    ("claude", re.compile(r"\bclaude", re.I)),
    ("gemini", re.compile(r"\bgemini", re.I)),
    ("llama", re.compile(r"\bllama", re.I)),
    ("mistral", re.compile(r"\bmistral", re.I)),
    ("qwen", re.compile(r"\bqwen", re.I)),
    ("deepseek", re.compile(r"\bdeepseek", re.I)),
    ("human", re.compile(r"\bhuman|人工|人写", re.I)),
]


def guess_generator(model: str) -> str:
    """从模型名猜生成方式。"""
    for label, pat in GEN_PATTERNS:
        if pat.search(model or ""):
            return label
    return "unknown"


# ---------------------------------------------------------------------------
# 不确定度
# ---------------------------------------------------------------------------

# 从文本里能判出的「机器味」信号：这些提示可能标在数据里
UNCERTAINTY_MARKERS = [
    (re.compile(r"^\s*(as an ai|作为一个[ai人工智能])", re.I | re.M), "自我指称"),
    (re.compile(r"\b(i cannot|i can't|as an ai)\b", re.I), "能力拒绝"),
    (re.compile(r"(\[待补充\]|【.*?】|<[a-z_]+>)", re.I), "模板占位"),
    (re.compile(r"(\bTODO\b|\bTBD\b)", re.I), "未完成标记"),
    (re.compile(r"(注意：以下内容为示例|示例数据|example only)", re.I), "示例声明"),
    (re.compile(r"(.)\1{4,}", re.S), "字符重复"),
    (re.compile(r"(。){3,}"), "标点重复"),
]


def assess_uncertainty(text: str) -> dict:
    """评估一条合成数据的不确定度。"""
    signals: list[str] = []
    for pat, label in UNCERTAINTY_MARKERS:
        if pat.search(text):
            signals.append(label)

    score = min(1.0, len(signals) * 0.3)
    if not signals:
        level = "low"
    elif score < 0.5:
        level = "medium"
    else:
        level = "high"

    return {"level": level, "score": round(score, 2), "signals": signals}


# ---------------------------------------------------------------------------
# 打标
# ---------------------------------------------------------------------------

def make_label(record: dict, text_field: str, index: int) -> dict:
    """给一条数据打上出生标签。"""
    text = record.get(text_field, "")
    if not isinstance(text, str):
        text = json.dumps(text, ensure_ascii=False)

    model = str(record.get("model") or record.get("generated_by") or "")
    generated_by = record.get("generated_by") or guess_generator(model)

    filter_criteria = record.get("filter_criteria") or record.get("criteria")
    if not filter_criteria:
        # 没写筛选依据就标成「未标注」——不替它编
        filter_criteria = "未标注"

    unc = record.get("uncertainty")
    if isinstance(unc, (int, float)):
        uncertainty = {"level": "machine", "score": float(unc), "signals": []}
    else:
        uncertainty = assess_uncertainty(text)

    label = {
        "generated_by": generated_by,
        "generated_at": record.get("generated_at"),
        "filter_criteria": filter_criteria,
        "uncertainty": uncertainty,
        "source_ref": record.get("source_ref"),
        "review_status": record.get("review_status", "unreviewed"),
        "labelled_index": index,
    }
    return label


# ---------------------------------------------------------------------------
# 审计
# ---------------------------------------------------------------------------

def audit(records: list[dict], labels: list[dict], text_field: str) -> dict:
    """审计一批合成数据的标签质量。"""
    by_generator = Counter(l["generated_by"] for l in labels)
    by_review = Counter(l["review_status"] for l in labels)
    by_uncertainty = Counter(l["uncertainty"]["level"] for l in labels)

    no_filter = [i for i, l in enumerate(labels) if l["filter_criteria"] == "未标注"]
    no_source = [i for i, l in enumerate(labels) if not l["source_ref"]]
    no_time = [i for i, l in enumerate(labels) if not l["generated_at"]]
    unreviewed = [i for i, l in enumerate(labels)
                  if l["review_status"] == "unreviewed"]
    high_unc = [i for i, l in enumerate(labels)
                if l["uncertainty"]["level"] == "high"]

    # 混入真实数据了吗：找没有标签的记录
    unlabeled = [i for i, l in enumerate(labels) if l is None]

    return {
        "total": len(records),
        "by_generator": dict(by_generator),
        "by_review": dict(by_review),
        "by_uncertainty": dict(by_uncertainty),
        "missing_filter_criteria": no_filter,
        "missing_source_ref": no_source,
        "missing_generated_at": no_time,
        "unreviewed": unreviewed,
        "high_uncertainty": high_unc,
        "unlabeled": unlabeled,
        "summary": {
            "generator_count": len(by_generator),
            "missing_filter_count": len(no_filter),
            "missing_source_count": len(no_source),
            "unreviewed_count": len(unreviewed),
            "high_uncertainty_count": len(high_unc),
        },
    }


# ---------------------------------------------------------------------------
# 输入
# ---------------------------------------------------------------------------

def load_records(path: str) -> list[dict]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read().strip()
    except OSError as e:
        raise ValueError(f"读不了 {path}：{e}") from e
    if not raw:
        return []
    if raw.startswith("["):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON 解析失败：{e}") from e
        return [x for x in data if isinstance(x, dict)]

    rows: list[dict] = []
    for lineno, line in enumerate(raw.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"第 {lineno} 行 JSON 解析失败：{e}") from e
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def render(audit_result: dict) -> str:
    out: list[str] = []
    s = audit_result["summary"]
    out.append("合成数据标签审计")
    out.append("=" * 60)
    out.append(f"记录数 {audit_result['total']}")
    out.append("")

    out.append("生成方式分布：")
    for k, v in sorted(audit_result["by_generator"].items(),
                       key=lambda kv: -kv[1]):
        out.append(f"  {k:<16} {v}")
    out.append("")

    out.append("不确定度分布：")
    for k, v in sorted(audit_result["by_uncertainty"].items()):
        out.append(f"  {k:<16} {v}")
    out.append("")

    out.append("人工复核状态：")
    for k, v in sorted(audit_result["by_review"].items()):
        out.append(f"  {k:<16} {v}")
    out.append("")

    issues = [
        ("没写筛选依据", audit_result["missing_filter_criteria"],
         "筛掉什么等于决定了留下什么，这一项必须写"),
        ("没写来源引用", audit_result["missing_source_ref"],
         "来源引用断了，将来查不回去"),
        ("没写生成时间", audit_result["missing_generated_at"],
         "没有时间就不知道这批数据是什么时候的模型产的"),
        ("未经复核", audit_result["unreviewed"],
         "机器标出来的标签还需要人过一遍"),
        ("高不确定度", audit_result["high_uncertainty"],
         "这些条目带着明显的机器味信号"),
    ]
    for label, idxs, why in issues:
        if idxs:
            out.append(f"★ {label}（{len(idxs)} 条）：{why}")
            shown = ", ".join(str(i) for i in idxs[:10])
            more = " …" if len(idxs) > 10 else ""
            out.append(f"    索引 {shown}{more}")
    out.append("")
    out.append("注：标签是给数据附加的元信息，不改变数据内容本身。")
    return "\n".join(out).rstrip()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="synthlabel",
        description="给合成数据标注它的生成方式与可信度（仅依赖标准库）",
        epilog=(
            "数据格式：\n"
            "  {\"text\":\"...\",\"model\":\"gpt-4o\",\"filter_criteria\":\"长度>200\"}\n"
            "  python synthlabel.py --data synth.jsonl --label-out labeled.jsonl\n"
            "  python synthlabel.py --data synth.jsonl --audit\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--data", required=True, help="数据文件")
    ap.add_argument("--text-field", default="text", help="正文字段")
    ap.add_argument("--label-out", help="写出打好标签的数据")
    ap.add_argument("--audit", action="store_true", help="只做审计，不写文件")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args(argv)

    try:
        records = load_records(args.data)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2

    if not records:
        print("没有数据。", file=sys.stderr)
        return 2

    labels = [make_label(r, args.text_field, i) for i, r in enumerate(records)]

    if args.label_out:
        try:
            with open(args.label_out, "w", encoding="utf-8") as f:
                for rec, label in zip(records, labels):
                    out = dict(rec)
                    out["_synth_label"] = label
                    f.write(json.dumps(out, ensure_ascii=False) + "\n")
        except OSError as e:
            print(f"写不了文件：{e}", file=sys.stderr)
            return 2
        print(f"已写出 {len(records)} 条带标签的数据 → {args.label_out}")

    if args.audit:
        result = audit(records, labels, args.text_field)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(render(result))
        s = result["summary"]
        return 1 if (s["missing_filter_count"] or s["missing_source_count"]) else 0

    if not args.label_out:
        print("需要 --label-out 或 --audit 其中之一。", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
