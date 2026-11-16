# credit-decision-service

信贷准入决策服务：把「8 条准入规则」从业务口径抽成可配置 YAML，用统一规则引擎输出**通过 / 拒绝 / 人工**三态决策，并提供 FastAPI 接口与阈值权衡分析。

数据为 Kaggle *Give Me Some Credit* 公开数据，仅用于学习与作品展示，不涉及任何真实客户信息。

## 项目结构

```
credit-decision-service/
├─ PROJECT.md              # 项目宪法：字段口径、清洗规则、规则口径、指标定义（不可随意改）
├─ rules.yaml              # 8 条规则（HARD 3 / SOFT 5）+ soft_fail_threshold
├─ rules.py                # 规则引擎：正则解析 condition，evaluate() 输出三态
├─ clean_and_bin.py        # 清洗 + 特征构造 + 等频分箱，产出 cleaned.csv 等
├─ metrics.py              # 全量跑规则，算通过率/坏账率/误杀率 + 阈值 1-5 扫描
├─ main.py                 # FastAPI：POST /decision、GET /metrics、GET /health
├─ test_decision.py        # pytest：覆盖 通过 / 拒绝 / 人工 三条路径
├─ bin_bad_rate.csv        # 4 个字段的 5 等频分箱坏账率（阈值依据）
├─ clean_before_after.csv  # 清洗前后对比（逐条对应清洗规则 1-6）
├─ strategy_tradeoff.csv   # soft_threshold 1-5 的通过率/坏账率/误杀率权衡表
├─ metrics.json            # 基准阈值 = 2 的指标快照（/metrics 接口直接读它）
├─ cleaned.csv             # 清洗后全量数据（150,000 行 × 16 列，可直接复用）
├─ decision_sample.json    # /decision 的示例返回
├─ pytest_output.txt       # pytest -v 运行记录
├─ docs/                   # 环境说明等文档
└─ screenshots/            # 运行截图
```

## 快速开始

```bash
python -m venv venv
# Windows: venv\Scripts\activate.bat   （PowerShell 用 .\venv\Scripts\Activate.ps1）
pip install -r requirements.txt

python clean_and_bin.py    # 清洗 + 分箱
python metrics.py          # 指标 + 阈值扫描
pytest test_decision.py -v # 3 个用例
uvicorn main:app --reload  # http://127.0.0.1:8000/docs
```

原始数据需自行从 Kaggle 下载 `cs-training.csv` 放到 `data/`（该目录的 csv 已被 .gitignore 排除）。

## 规则设计（与 PROJECT.md 一致）

| 分组 | code | 条件 | 业务含义 |
| --- | --- | --- | --- |
| HARD | MIN_AGE | `age < 21` | 年龄不足 |
| HARD | EVER_90DPD | `ever_90dpd == 1` | 有 90+ 天逾期史 |
| HARD | HIGH_REVOLVING | `revolving_util > 0.8` | 循环额度使用率过高 |
| SOFT | EVER_60DPD | `ever_60dpd == 1` | 有 60-89 天逾期史 |
| SOFT | HIGH_DTI | `debt_ratio > 0.5` | 负债收入比过高 |
| SOFT | LOW_INCOME | `monthly_income < 3000` | 月收入偏低 |
| SOFT | MANY_LINES | `open_credit_lines > 15` | 多头借贷 |
| SOFT | INCOME_MISSING | `income_missing == 1` | 收入信息缺失 |

决策三态：HARD 命中 → **拒绝**；SOFT 命中数 ≥ `soft_fail_threshold`(2) → **人工**；否则 → **通过**。

## 基准结果（150,000 样本，soft_fail_threshold = 2）

| 指标 | 值 |
| --- | --- |
| 通过率 | 57.73% |
| 通过件坏账率 | 2.88%（整体坏账率 6.68%） |
| 误杀率 | 39.92% |
| 拒绝率 / 转人工率 | 18.92% / 23.36% |

阈值扫描（`strategy_tradeoff.csv`）：

| soft_threshold | 通过率 | 通过件坏账率 | 误杀率 |
| --- | --- | --- | --- |
| 1 | 38.44% | 2.08% | 59.66% |
| 2（基准） | 57.73% | 2.88% | 39.92% |
| 3 | 79.06% | 2.92% | 17.75% |
| 4 | 81.03% | 3.04% | 15.81% |
| 5 | 81.08% | 3.05% | 15.76% |

基准取 2 是保守风险偏好下的选择；从表可见放宽到 3 只用 +0.04pp 的坏账率换来 +21.3pp 通过率，这一权衡在 `strategy_tradeoff.csv` 中可量化复核。

## 接口

```bash
curl -X POST http://127.0.0.1:8000/decision \
  -H "Content-Type: application/json" \
  -d '{"age":45,"revolving_util":0.3,"debt_ratio":0.2,"monthly_income":8000,
       "open_credit_lines":5,"ever_90dpd":1}'
```

```json
{"decision":"拒绝","hard_hits":["EVER_90DPD"],"soft_hits":[],"soft_hit_count":0}
```

- `GET /decision` 的完整字段见 `/docs`（Swagger UI）
- `GET /metrics` 返回 `metrics.json` 全量指标，与离线分析共用同一份结果

## 说明

- 规则条件只允许 `< > <= >= == !=` 六种运算符，字段名一律内部 snake_case；字段缺失视为不命中。
- 规则逻辑只有 `rules.py` 一份实现，`main.py` 与 `metrics.py` 均直接 import，避免口径漂移。
