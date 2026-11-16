# -*- coding: utf-8 -*-
"""
stage3：全量跑规则，算三大指标 + 阈值扫描。

指标口径严格遵循 PROJECT.md「指标定义」：
- 通过率      = 决策为“通过”的样本数 / 总样本数
- 通过件坏账率 = 决策为“通过”的样本中 bad_flag 的均值
- 误杀率      = 好客户（bad_flag=0）中被决策为“拒绝”或“人工”的比例

规则逻辑只有一份，来自 rules.evaluate，本文件不重复实现任何条件判断。
"""

from __future__ import annotations

import json
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import pandas as pd

from rules import evaluate, load_rules

BASE_DIR = Path(__file__).resolve().parent
CLEANED_PATH = BASE_DIR / "cleaned.csv"
TRADEOFF_PATH = BASE_DIR / "strategy_tradeoff.csv"
METRICS_PATH = BASE_DIR / "metrics.json"

BASE_THRESHOLD = 2          # PROJECT.md 规定的基准阈值
SWEEP_THRESHOLDS = [1, 2, 3, 4, 5]

DECISION_PASS = "通过"
DECISION_REJECT = "拒绝"
DECISION_REVIEW = "人工"


def ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def main() -> None:
    started = time.perf_counter()

    print("=" * 78)
    print("0. 读取数据")
    print("=" * 78)
    if not CLEANED_PATH.exists():
        raise FileNotFoundError(f"找不到清洗后数据：{CLEANED_PATH}")
    df = pd.read_csv(CLEANED_PATH, encoding="utf-8-sig")
    total = len(df)
    print(f"文件：{CLEANED_PATH.name}   行数：{total:,}   列数：{df.shape[1]}")
    print(f"bad_flag 分布：好客户 {(df['bad_flag'] == 0).sum():,}   坏客户 {(df['bad_flag'] == 1).sum():,}")

    # 逐行特征字典（去掉标签，evaluate 不需要）
    features_list = [
        {k: v for k, v in record.items() if k != "bad_flag"}
        for record in df.to_dict("records")
    ]
    labels = df["bad_flag"].astype(int).tolist()

    # ------------------------------------------------------------------
    print()
    print("=" * 78)
    print(f"1. 逐行调用 rules.evaluate（每行 {len(SWEEP_THRESHOLDS)} 次，共 {total * len(SWEEP_THRESHOLDS):,} 次调用）")
    print("=" * 78)

    sweep_rows = []
    # 预置全部 8 条规则，保证 0 命中的规则也出现在分布里
    hit_counter: Counter = Counter({rule["code"]: 0 for rule in load_rules()["rules"]})
    baseline_detail = None

    for threshold in SWEEP_THRESHOLDS:
        n_pass = n_reject = n_manual = 0
        bad_in_pass = 0
        good_total = 0
        good_killed = 0
        t0 = time.perf_counter()

        for features, label in zip(features_list, labels):
            result = evaluate(features, soft_threshold=threshold)
            decision = result["decision"]

            if decision == DECISION_PASS:
                n_pass += 1
                bad_in_pass += label
            elif decision == DECISION_REJECT:
                n_reject += 1
            else:
                n_manual += 1

            # 好客户中被拒或被转人工 -> 误杀
            if label == 0:
                good_total += 1
                if decision in (DECISION_REJECT, DECISION_REVIEW):
                    good_killed += 1

            # 规则命中分布只统计一次（与阈值无关）
            if threshold == BASE_THRESHOLD:
                for code in result["hard_hits"] + result["soft_hits"]:
                    hit_counter[code] += 1

        row = {
            "soft_threshold": threshold,
            "approval_rate": ratio(n_pass, total),
            "bad_rate_on_approved": ratio(bad_in_pass, n_pass),
            "false_kill_rate": ratio(good_killed, good_total),
            "reject_rate": ratio(n_reject, total),
            "manual_rate": ratio(n_manual, total),
        }
        sweep_rows.append(row)

        if threshold == BASE_THRESHOLD:
            baseline_detail = {
                "n_pass": n_pass,
                "n_reject": n_reject,
                "n_manual": n_manual,
                "bad_in_pass": bad_in_pass,
                "good_total": good_total,
                "good_killed": good_killed,
            }

        elapsed = time.perf_counter() - t0
        print(
            f"  threshold={threshold}  通过 {n_pass:>6,}  拒绝 {n_reject:>6,}  人工 {n_manual:>6,}  "
            f"通过率 {row['approval_rate']:.4f}  通过件坏账率 {row['bad_rate_on_approved']:.4f}  "
            f"误杀率 {row['false_kill_rate']:.4f}  [{elapsed:.1f}s]"
        )

    tradeoff = pd.DataFrame(
        sweep_rows,
        columns=[
            "soft_threshold",
            "approval_rate",
            "bad_rate_on_approved",
            "false_kill_rate",
            "reject_rate",
            "manual_rate",
        ],
    )

    print()
    print("=" * 78)
    print("2. 基准阈值 = 2 的核心指标（口径见 PROJECT.md「指标定义」）")
    print("=" * 78)
    baseline = tradeoff.loc[tradeoff["soft_threshold"] == BASE_THRESHOLD].iloc[0]
    print(f"  通过率 approval_rate            = {baseline['approval_rate']:.4f}  ({baseline['approval_rate'] * 100:.2f}%)")
    print(f"  通过件坏账率 bad_rate_on_approved = {baseline['bad_rate_on_approved']:.4f}  ({baseline['bad_rate_on_approved'] * 100:.2f}%)")
    print(f"  误杀率 false_kill_rate          = {baseline['false_kill_rate']:.4f}  ({baseline['false_kill_rate'] * 100:.2f}%)")
    print(f"  拒绝率 reject_rate              = {baseline['reject_rate']:.4f}")
    print(f"  转人工率 manual_rate            = {baseline['manual_rate']:.4f}")
    print(f"  样本计数：通过 {baseline_detail['n_pass']:,} / 拒绝 {baseline_detail['n_reject']:,} / 人工 {baseline_detail['n_manual']:,}")

    print()
    print("=" * 78)
    print("3. 规则命中分布（基准阈值下，每条规则命中的样本行数）")
    print("=" * 78)
    # 按 rules.yaml 中的定义顺序输出，保证 8 条规则齐全（未命中记 0）
    rule_hit_distribution = {
        rule["code"]: int(hit_counter.get(rule["code"], 0))
        for rule in load_rules()["rules"]
    }
    for code, cnt in rule_hit_distribution.items():
        print(f"  {code:<15} {cnt:>7,}  ({cnt / total * 100:5.2f}%)")

    # ------------------------------------------------------------------
    tradeoff.to_csv(TRADEOFF_PATH, index=False, encoding="utf-8-sig")

    metrics = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data_file": CLEANED_PATH.name,
        "total_samples": total,
        "soft_fail_threshold": BASE_THRESHOLD,
        "approval_rate": round(float(baseline["approval_rate"]), 6),
        "bad_rate_on_approved": round(float(baseline["bad_rate_on_approved"]), 6),
        "false_kill_rate": round(float(baseline["false_kill_rate"]), 6),
        "reject_rate": round(float(baseline["reject_rate"]), 6),
        "manual_rate": round(float(baseline["manual_rate"]), 6),
        "counts": {
            "pass": baseline_detail["n_pass"],
            "reject": baseline_detail["n_reject"],
            "manual": baseline_detail["n_manual"],
            "good_total": baseline_detail["good_total"],
            "bad_total": total - baseline_detail["good_total"],
            "bad_in_pass": baseline_detail["bad_in_pass"],
            "good_killed": baseline_detail["good_killed"],
        },
        "rule_hit_distribution": rule_hit_distribution,
        "definitions": {
            "approval_rate": "决策为“通过”的样本数 / 总样本数",
            "bad_rate_on_approved": "决策为“通过”的样本中 bad_flag 的均值",
            "false_kill_rate": "好客户（bad_flag=0）中被决策为“拒绝”或“人工”的比例",
        },
    }
    with METRICS_PATH.open("w", encoding="utf-8") as fh:
        json.dump(metrics, fh, ensure_ascii=False, indent=2)

    print()
    print("=" * 78)
    print("4. 写出文件")
    print("=" * 78)
    print(f"  {TRADEOFF_PATH.name:<24} {TRADEOFF_PATH.stat().st_size:>8,} 字节")
    print(f"  {METRICS_PATH.name:<24} {METRICS_PATH.stat().st_size:>8,} 字节")

    print()
    print("=" * 78)
    print(f"5. {TRADEOFF_PATH.name} 全文")
    print("=" * 78)
    back = pd.read_csv(TRADEOFF_PATH, encoding="utf-8-sig")
    print(back.to_string(index=False))

    print()
    print("=" * 78)
    print(f"6. {METRICS_PATH.name} 全文")
    print("=" * 78)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))

    print()
    print(f"总耗时 {time.perf_counter() - started:.1f}s")


if __name__ == "__main__":
    main()
