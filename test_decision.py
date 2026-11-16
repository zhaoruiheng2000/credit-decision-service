# -*- coding: utf-8 -*-
"""
三条决策路径的接口测试：通过 / 拒绝 / 人工。

运行：pytest test_decision.py -v
"""

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

# 基准样本：各项指标均正常，8 条规则全部不命中 -> 通过
BASE = {
    "age": 45,
    "revolving_util": 0.30,
    "debt_ratio": 0.20,
    "monthly_income": 8000,
    "open_credit_lines": 5,
    "n_90_dpd": 0,
    "n_60_89_dpd": 0,
    "n_30_59_dpd": 0,
    "real_estate_lines": 1,
    "n_dependents": 1,
    "ever_90dpd": 0,
    "ever_60dpd": 0,
    "income_missing": 0,
}


def test_pass_path():
    """用例 1：全部正常 -> 通过"""
    resp = client.post("/decision", json={**BASE})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["decision"] == "通过", body
    assert body["hard_hits"] == [], body
    assert body["soft_hit_count"] == 0, body


def test_reject_path_hard_rule():
    """用例 2：ever_90dpd=1 -> HARD 命中 -> 拒绝"""
    resp = client.post("/decision", json={**BASE, "ever_90dpd": 1})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["decision"] == "拒绝", body
    assert "EVER_90DPD" in body["hard_hits"], body


def test_manual_review_path_soft_rules():
    """用例 3：ever_60dpd=1 且 income_missing=1 -> SOFT 命中 2 条 -> 人工"""
    resp = client.post("/decision", json={**BASE, "ever_60dpd": 1, "income_missing": 1})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["decision"] == "人工", body
    assert body["soft_hit_count"] >= 2, body
    assert body["hard_hits"] == [], body
    assert set(body["soft_hits"]) == {"EVER_60DPD", "INCOME_MISSING"}, body
