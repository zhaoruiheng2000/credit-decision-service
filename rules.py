# -*- coding: utf-8 -*-
"""
规则引擎：读取 rules.yaml，用正则解析 condition，输出三态决策。

口径严格来自 PROJECT.md：
- 8 条规则（HARD 3 / SOFT 5），soft_fail_threshold = 2
- HARD 命中 -> 拒绝；SOFT 命中数 >= 阈值 -> 人工；否则 -> 通过
- condition 只使用内部字段名，仅支持 < > <= >= == != 六种运算符
- 字段缺失视为不命中
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

RULES_PATH = Path(__file__).resolve().with_name("rules.yaml")

# 只接受六种运算符；先匹配两字符运算符，避免 "<=" 被误拆成 "<" + "="
CONDITION_RE = re.compile(
    r"^\s*(?P<field>[A-Za-z_][A-Za-z0-9_]*)\s*(?P<op><=|>=|==|!=|<|>)\s*(?P<value>.+?)\s*$"
)
ALLOWED_OPS = {"<", ">", "<=", ">=", "==", "!="}

DECISION_PASS = "通过"
DECISION_REJECT = "拒绝"
DECISION_REVIEW = "人工"


def _parse_value(raw: str) -> Any:
    """把 condition 右侧的字面量转成 int / float / bool / str。"""
    text = raw.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ('"', "'"):
        return text[1:-1]
    lowered = text.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        pass
    return text


def _to_number(value: Any) -> Optional[float]:
    """尽力把值转成数值；bool 也按 0/1 处理。"""
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _compare(actual: Any, op: str, expected: Any) -> bool:
    left_num, right_num = _to_number(actual), _to_number(expected)
    if left_num is not None and right_num is not None:
        left, right = left_num, right_num
    else:
        left, right = actual, expected

    if op == "<":
        return left < right
    if op == ">":
        return left > right
    if op == "<=":
        return left <= right
    if op == ">=":
        return left >= right
    if op == "==":
        return left == right
    if op == "!=":
        return left != right
    raise ValueError(f"不支持的运算符：{op}")


@lru_cache(maxsize=1)
def load_rules() -> Dict[str, Any]:
    """读取并解析 rules.yaml（带缓存，修改后用 load_rules.cache_clear() 重载）。"""
    if not RULES_PATH.exists():
        raise FileNotFoundError(f"规则文件不存在：{RULES_PATH}")

    with RULES_PATH.open("r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh) or {}

    policy = config.get("policy") or {}
    raw_rules = config.get("rules") or []
    if not raw_rules:
        raise ValueError(f"{RULES_PATH.name} 中没有任何规则")

    parsed: List[Dict[str, Any]] = []
    for index, item in enumerate(raw_rules, start=1):
        code = str(item.get("code", "")).strip()
        condition = str(item.get("condition", "")).strip()
        severity = str(item.get("severity", "")).strip().upper()
        reason = str(item.get("reason", "")).strip()

        if not code:
            raise ValueError(f"第 {index} 条规则缺少 code")
        if severity not in {"HARD", "SOFT"}:
            raise ValueError(f"规则 {code} 的 severity 只能是 HARD/SOFT，实际为 {severity!r}")

        match = CONDITION_RE.match(condition)
        if not match:
            raise ValueError(f"规则 {code} 的 condition 无法解析（只支持六种比较运算符）：{condition!r}")
        op = match.group("op")
        if op not in ALLOWED_OPS:
            raise ValueError(f"规则 {code} 使用了不支持的运算符：{op!r}")

        parsed.append({
            "code": code,
            "condition": condition,
            "field": match.group("field"),
            "op": op,
            "value": _parse_value(match.group("value")),
            "severity": severity,
            "reason": reason,
        })

    return {
        "soft_fail_threshold": int(policy.get("soft_fail_threshold", 2)),
        "rules": parsed,
    }


def evaluate(features: Dict[str, Any], soft_threshold: int = 2) -> Dict[str, Any]:
    """
    对单个样本执行 8 条规则。

    参数
    ----
    features : 内部字段名字典，例如 {"age": 45, "ever_90dpd": 0, ...}
    soft_threshold : SOFT 命中数达到多少转人工，默认 2（与 PROJECT.md 一致）

    返回
    ----
    {"decision": "通过"/"拒绝"/"人工", "hard_hits": [...], "soft_hits": [...], "soft_hit_count": int}
    """
    if features is None:
        features = {}
    threshold = int(soft_threshold)

    hard_hits: List[str] = []
    soft_hits: List[str] = []

    for rule in load_rules()["rules"]:
        field_name = rule["field"]

        # 字段缺失 / 值为 None：视为不命中
        if field_name not in features:
            continue
        actual = features[field_name]
        if actual is None:
            continue

        try:
            hit = _compare(actual, rule["op"], rule["value"])
        except TypeError:
            # 类型不可比较（如字符串与数字混用），按不命中处理，避免接口 500
            continue

        if hit:
            if rule["severity"] == "HARD":
                hard_hits.append(rule["code"])
            else:
                soft_hits.append(rule["code"])

    if hard_hits:
        decision = DECISION_REJECT
    elif len(soft_hits) >= threshold:
        decision = DECISION_REVIEW
    else:
        decision = DECISION_PASS

    return {
        "decision": decision,
        "hard_hits": hard_hits,
        "soft_hits": soft_hits,
        "soft_hit_count": len(soft_hits),
    }


if __name__ == "__main__":
    cfg = load_rules()
    hard = [r["code"] for r in cfg["rules"] if r["severity"] == "HARD"]
    soft = [r["code"] for r in cfg["rules"] if r["severity"] == "SOFT"]
    print(f"规则总数：{len(cfg['rules'])}  HARD {len(hard)} 条  SOFT {len(soft)} 条")
    print(f"soft_fail_threshold：{cfg['soft_fail_threshold']}")
    print(f"HARD：{hard}")
    print(f"SOFT：{soft}")
    demo = {"age": 45, "ever_90dpd": 0, "ever_60dpd": 0, "revolving_util": 0.3,
            "debt_ratio": 0.2, "monthly_income": 8000, "open_credit_lines": 5,
            "income_missing": 0}
    print("示例样本：", evaluate(demo))
