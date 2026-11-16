# 项目宪法：信贷准入决策服务

## 数据来源
Kaggle GiveMeSomeCredit，公开数据/模拟数据，仅用于学习与作品展示，不涉及真实客户信息。

## 字段口径（原始列名 → 内部字段名）
- SeriousDlqin2yrs → bad_flag（1=坏客户，90天以上逾期）
- RevolvingUtilizationOfUnsecuredLines → revolving_util
- age → age
- NumberOfTime30-59DaysPastDueNotWorse → n_30_59_dpd
- DebtRatio → debt_ratio
- MonthlyIncome → monthly_income
- NumberOfOpenCreditLinesAndLoans → open_credit_lines
- NumberOfTimes90DaysLate → n_90_dpd
- NumberRealEstateLoansOrLines → real_estate_lines
- NumberOfTime60-89DaysPastDueNotWorse → n_60_89_dpd
- NumberOfDependents → n_dependents
- 衍生字段：income_missing、ever_90dpd、ever_60dpd、debt_per_line、income_per_person

## 清洗规则（固定，不得更改）
1. 删除 Unnamed: 0 列，标签重命名为 bad_flag
2. age <= 0 视为异常，置为缺失后用中位数填充
3. revolving_util 截尾至 1.0
4. 所有逾期次数字段截尾至 10
5. monthly_income 缺失用中位数填充，新增 income_missing 指示列
6. 构造 ever_90dpd = (n_90_dpd > 0)、ever_60dpd = (n_60_89_dpd > 0)、debt_per_line = debt_ratio / (open_credit_lines + 1)、income_per_person = monthly_income / (n_dependents + 1)

## 规则引擎口径（固定）
- 规则总数：8 条
- HARD 3 条：age < 21、ever_90dpd == 1、revolving_util > 0.8
- SOFT 5 条：ever_60dpd == 1、debt_ratio > 0.5、monthly_income < 3000、open_credit_lines > 15、income_missing == 1
- soft_fail_threshold: 2
- 决策三态：HARD 命中 → 拒绝；SOFT 命中数 >= 2 → 人工；否则 → 通过
- rules.yaml 中 condition 一律使用内部字段名（snake_case），不得使用原始列名

## 指标定义
- 通过率 = 决策为“通过”的样本数 / 总样本数
- 通过件坏账率 = 决策为“通过”的样本中 bad_flag 的均值
- 误杀率 = 好客户（bad_flag=0）中被决策为“拒绝”或“人工”的比例

## 简历句子（N=8，不得改）
用 pandas 完成清洗与分箱，将 8 条准入规则抽成 YAML（HARD/SOFT 分层，阈值依据分箱坏账率）；基于 FastAPI 提供 /decision 接口，返回“通过/拒绝/人工”及命中规则；扫描 SOFT 阈值生成通过率—坏账率—误杀率权衡表，量化阈值放松的边际代价并给出基准阈值理由；pytest 跑通 3 个用例覆盖三条决策路径。
