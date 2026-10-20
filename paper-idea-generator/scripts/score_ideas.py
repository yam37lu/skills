#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按九维评分计算论文 idea 的加权总分、排序与结论。

用法::

    python score_ideas.py ideas.json
    python score_ideas.py ideas.json --json result.json
    python score_ideas.py --template

输入 JSON 格式见 assets/scorecard-template.json：每个 idea 的 scores 必须包含
novelty / significance / fit / data / feasibility / compute / risk /
publishability / defensibility 九个键，取值 1-5（可为小数）。

默认权重与 references/evaluation.md 一致；可用 --weights 传入自定义权重
（九个键齐全，总和会被归一化），用于敏感性分析。

结论规则：硬约束一票否决优先于总分；其余按 4.0 / 3.4 / 2.8 分档。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DIMENSIONS = [
    ("novelty", "新颖", 0.20),
    ("significance", "价值", 0.15),
    ("fit", "契合", 0.15),
    ("data", "数据", 0.10),
    ("feasibility", "可行", 0.15),
    ("compute", "算力", 0.05),
    ("risk", "风险", 0.05),
    ("publishability", "发表", 0.10),
    ("defensibility", "可辩护", 0.05),
]

TEMPLATE = {
    "ideas": [
        {
            "id": "I1",
            "title": "工作标题",
            "scores": {key: 3 for key, _, _ in DIMENSIONS},
            "notes": "评分理由（可选）",
        }
    ]
}


def die(message: str) -> "NoReturn":
    print(f"错误：{message}", file=sys.stderr)
    raise SystemExit(1)


def load_weights(path: str | None) -> dict[str, float]:
    weights = {key: weight for key, _, weight in DIMENSIONS}
    if not path:
        return weights

    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        die(f"读取权重失败：{error}")

    missing = [key for key in weights if key not in raw]
    if missing:
        die(f"权重缺少字段：{', '.join(missing)}")
    unknown = [key for key in raw if key not in weights]
    if unknown:
        die(f"权重包含未知字段：{', '.join(unknown)}")

    total = sum(float(raw[key]) for key in weights)
    if total <= 0:
        die("权重之和必须大于 0")
    return {key: float(raw[key]) / total for key in weights}


def verdict_for(scores: dict[str, float], total: float) -> tuple[str, list[str]]:
    vetoes = []
    if scores["data"] <= 1:
        vetoes.append("数据不可得")
    if scores["feasibility"] <= 1:
        vetoes.append("技术可行性不足")
    if scores["defensibility"] <= 1:
        vetoes.append("已有同题工作")
    if scores["novelty"] <= 1 and scores["defensibility"] <= 2:
        vetoes.append("本质重复")

    if vetoes:
        return "否决：" + "、".join(vetoes), vetoes
    if total >= 4.0:
        if min(scores.values()) <= 2:
            return "B 可做（存在 ≤2 短板）", vetoes
        return "A 强推", vetoes
    if total >= 3.4:
        return "B 可做", vetoes
    if total >= 2.8:
        return "C 备选", vetoes
    return "D 放弃", vetoes


def score_idea(idea: dict, weights: dict[str, float]) -> dict:
    idea_id = str(idea.get("id") or "?").strip()
    title = str(idea.get("title") or "").strip()
    scores = idea.get("scores")
    if not isinstance(scores, dict):
        die(f"{idea_id} 缺少 scores 对象")

    missing = [key for key, _, _ in DIMENSIONS if key not in scores]
    if missing:
        die(f"{idea_id} 缺少评分：{', '.join(missing)}")

    clean: dict[str, float] = {}
    for key, _, _ in DIMENSIONS:
        try:
            value = float(scores[key])
        except (TypeError, ValueError):
            die(f"{idea_id} 的 {key} 不是数字")
        if not 1 <= value <= 5:
            die(f"{idea_id} 的 {key}={value} 超出 1-5")
        clean[key] = value

    total = sum(clean[key] * weights[key] for key, _, _ in DIMENSIONS)
    verdict, vetoes = verdict_for(clean, total)
    weak = [
        (label, clean[key])
        for key, label, _ in DIMENSIONS
        if clean[key] <= 2.5
    ]
    return {
        "id": idea_id,
        "title": title,
        "scores": clean,
        "total": round(total, 2),
        "verdict": verdict,
        "vetoes": vetoes,
        "weak": weak,
    }


def print_markdown(results: list[dict]) -> None:
    headers = ["排名", "Idea", "标题"] + [label for _, label, _ in DIMENSIONS] + ["加权", "结论"]
    print("| " + " | ".join(headers) + " |")
    print("|" + "|".join(["---"] * len(headers)) + "|")
    for rank, item in enumerate(results, start=1):
        cells = [str(rank), item["id"], item["title"] or "—"]
        cells += [f"{item['scores'][key]:g}" for key, _, _ in DIMENSIONS]
        cells += [f"{item['total']:.2f}", item["verdict"]]
        print("| " + " | ".join(cells) + " |")

    print("\n补强建议：")
    any_weak = False
    for item in results:
        if item["weak"]:
            any_weak = True
            detail = "、".join(f"{label} {value:g}" for label, value in item["weak"])
            print(f"- {item['id']}：{detail}")
    if not any_weak:
        print("- 无低于 2.5 的维度；仍需确认最高分维度有证据支撑。")


def main() -> None:
    parser = argparse.ArgumentParser(description="论文 idea 九维加权评分")
    parser.add_argument("input", nargs="?", help="评分 JSON 文件")
    parser.add_argument("--weights", help="可选：自定义权重 JSON（九维，自动归一化）")
    parser.add_argument("--json", dest="json_out", help="可选：把结果写入 JSON")
    parser.add_argument("--template", action="store_true", help="打印输入模板后退出")
    args = parser.parse_args()

    if args.template:
        print(json.dumps(TEMPLATE, ensure_ascii=False, indent=2))
        return
    if not args.input:
        parser.error("需要输入 JSON 文件（或用 --template 查看格式）")

    try:
        raw = json.loads(Path(args.input).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        die(f"读取评分文件失败：{error}")

    ideas = raw.get("ideas") if isinstance(raw, dict) else None
    if not isinstance(ideas, list) or not ideas:
        die("输入必须是 {\"ideas\": [...]}，且至少包含一个 idea")

    weights = load_weights(args.weights)
    results = [score_idea(idea, weights) for idea in ideas]
    results.sort(key=lambda item: (bool(item["vetoes"]), -item["total"], -item["scores"]["novelty"], item["id"]))

    print_markdown(results)

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps({"weights": weights, "results": results}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n结果已写入：{args.json_out}")


if __name__ == "__main__":
    main()
