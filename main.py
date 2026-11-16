# -*- coding: utf-8 -*-
"""
FastAPI 服务：POST /decision 接收内部字段名的请求体，调用 rules.evaluate 返回三态决策。

规则逻辑只有一份，位于 rules.py，本文件不做任何重复实现。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from rules import evaluate

METRICS_PATH = Path(__file__).resolve().with_name("metrics.json")

app = FastAPI(
    title="信贷准入决策服务",
    description="基于 8 条 HARD/SOFT 规则的信贷准入决策接口",
    version="0.1.0",
)


class DecisionRequest(BaseModel):
    """请求体：字段一律使用内部 snake_case 名（与 PROJECT.md 字段口径一致）。"""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    age: float = Field(default=40, description="年龄")
    revolving_util: float = Field(default=0.0, description="循环额度使用率，已截尾至 1.0")
    debt_ratio: float = Field(default=0.0, description="负债收入比")
    monthly_income: float = Field(default=5000.0, description="月收入，已用中位数填充")
    open_credit_lines: float = Field(default=5.0, description="未结清信贷账户数")
    n_90_dpd: float = Field(default=0.0, description="90 天以上逾期次数，已截尾至 10")
    n_60_89_dpd: float = Field(default=0.0, description="60-89 天逾期次数，已截尾至 10")
    n_30_59_dpd: float = Field(
        default=0.0,
        alias="NumberOfTime30-59DaysPastDueNotWorse",
        description="30-59 天逾期次数，保留原始列名作为 alias",
    )
    real_estate_lines: float = Field(default=0.0, description="房贷/不动产贷款笔数")
    n_dependents: float = Field(default=0.0, description="赡养人数")
    ever_90dpd: int = Field(default=0, description="是否曾有 90+ 天逾期：1=是")
    ever_60dpd: int = Field(default=0, description="是否曾有 60-89 天逾期：1=是")
    income_missing: int = Field(default=0, description="月收入是否缺失：1=缺失")
    bad_flag: Optional[int] = Field(default=None, description="真实标签，仅用于离线评估，可空")


class DecisionResponse(BaseModel):
    decision: str
    hard_hits: List[str]
    soft_hits: List[str]
    soft_hit_count: int


def _to_features(payload: DecisionRequest) -> dict:
    """把 Pydantic 模型摊平成 rules.evaluate 需要的内部字段名字典。"""
    return payload.model_dump(by_alias=False)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/metrics")
def metrics() -> dict:
    """直接读取离线生成的 metrics.json，保证接口与离线表是同一份结果。"""
    if not METRICS_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail=f"未找到 {METRICS_PATH.name}，请先执行 python metrics.py",
        )
    with METRICS_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


@app.post("/decision", response_model=DecisionResponse)
def decision(payload: DecisionRequest) -> dict:
    """调用统一规则引擎，返回决策与命中规则。"""
    return evaluate(_to_features(payload))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
