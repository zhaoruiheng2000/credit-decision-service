# -*- coding: utf-8 -*-
"""
stage1：清洗 + 特征构造 + 等频分箱

严格遵循 PROJECT.md 的字段口径与 6 条清洗规则（不改写规则本身）。
输入：data/cs-training.csv
输出：cleaned.csv / clean_before_after.csv / bin_bad_rate.csv（均 utf-8-sig）
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent
SRC = BASE / "data" / "cs-training.csv"

# 原始列名 -> 内部字段名（PROJECT.md 字段口径）
RENAME = {
    "SeriousDlqin2yrs": "bad_flag",
    "RevolvingUtilizationOfUnsecuredLines": "revolving_util",
    "NumberOfTime30-59DaysPastDueNotWorse": "n_30_59_dpd",
    "DebtRatio": "debt_ratio",
    "MonthlyIncome": "monthly_income",
    "NumberOfOpenCreditLinesAndLoans": "open_credit_lines",
    "NumberOfTimes90DaysLate": "n_90_dpd",
    "NumberRealEstateLoansOrLines": "real_estate_lines",
    "NumberOfTime60-89DaysPastDueNotWorse": "n_60_89_dpd",
    "NumberOfDependents": "n_dependents",
}
DPD_COLS = ["n_30_59_dpd", "n_90_dpd", "n_60_89_dpd"]
NEW_FEATURES = ["income_missing", "ever_90dpd", "ever_60dpd", "debt_per_line", "income_per_person"]
BIN_COLS = ["age", "monthly_income", "debt_ratio", "revolving_util"]


def line(title=""):
    print("\n" + "=" * 78)
    if title:
        print(title)
        print("=" * 78)


def miss_rate(s):
    return float(s.isna().mean())


def pct(x):
    return f"{x * 100:.2f}%"


def main():
    try:
        pd.set_option("display.width", 200)
        pd.set_option("display.max_columns", 60)
        pd.set_option("display.unicode.east_asian_width", True)
        pd.set_option("display.float_format", lambda v: f"{v:.4f}")
    except Exception:
        pass

    line("0. 读取原始数据")
    if not SRC.exists():
        sys.exit(f"[FATAL] 找不到输入文件：{SRC}")
    df = pd.read_csv(SRC, encoding="utf-8-sig")
    df_raw = df.copy()  # 清洗前快照，用于 before/after 对比
    print(f"文件：{SRC}")
    print(f"原始形状：{df.shape[0]:,} 行 × {df.shape[1]} 列")
    print(f"原始列名：{list(df.columns)}")

    # ---------------- 规则 1 ----------------
    line("规则 1：删除 Unnamed: 0 列，标签重命名为 bad_flag")
    rows_before, cols_before = df.shape
    if "Unnamed: 0" in df.columns:
        df = df.drop(columns=["Unnamed: 0"])
        print("已删除列 Unnamed: 0")
    else:
        print("未发现 Unnamed: 0 列，跳过删除")
    df = df.rename(columns=RENAME)
    print(f"列数：{cols_before} -> {df.shape[1]}")
    print(f"行数：{rows_before:,} -> {df.shape[0]:,}（删列不改行数）")
    print(f"重命名后列名：{list(df.columns)}")
    assert "bad_flag" in df.columns, "bad_flag 标签列缺失"

    # ---------------- 规则 2 ----------------
    line("规则 2：age <= 0 视为异常，置为缺失后用中位数填充")
    print(f"清洗前：行数 {df.shape[0]:,}，age 缺失率 {pct(miss_rate(df['age']))}，age 最小值 {df['age'].min()}")
    age_bad = int((df["age"] <= 0).sum())
    df.loc[df["age"] <= 0, "age"] = np.nan
    age_median = df["age"].median()
    df["age"] = df["age"].fillna(age_median)
    print(f"命中 age<=0 的记录数：{age_bad:,}  -> 已置为缺失")
    print(f"用于填充的 age 中位数：{age_median}")
    print(f"清洗后：行数 {df.shape[0]:,}，age 缺失率 {pct(miss_rate(df['age']))}，age 最小值 {df['age'].min()}")

    # ---------------- 规则 3 ----------------
    line("规则 3：revolving_util 截尾至 1.0")
    ru_max_before = float(df["revolving_util"].max())
    ru_over = int((df["revolving_util"] > 1.0).sum())
    df["revolving_util"] = df["revolving_util"].clip(upper=1.0)
    print(f"清洗前：最大值 {ru_max_before:,.4f}，>1.0 的记录 {ru_over:,} 条（占 {pct(ru_over / len(df))}）")
    print(f"清洗后：最大值 {df['revolving_util'].max():,.4f}，行数 {df.shape[0]:,} 不变")

    # ---------------- 规则 4 ----------------
    line("规则 4：所有逾期次数字段截尾至 10")
    for c in DPD_COLS:
        before_max = float(df[c].max())
        over = int((df[c] > 10).sum())
        df[c] = df[c].clip(upper=10)
        print(f"{c:<12} 清洗前 max={before_max:>6.0f}  >10 的 {over:>6,} 条  ->  清洗后 max={df[c].max():>3.0f}")
    print(f"行数：{df.shape[0]:,} 不变")

    # ---------------- 规则 5 ----------------
    line("规则 5：monthly_income 缺失用中位数填充，新增 income_missing 指示列")
    income_miss_before = miss_rate(df["monthly_income"])
    df["income_missing"] = df["monthly_income"].isna().astype(int)
    print(f"清洗前：monthly_income 缺失率 {pct(income_miss_before)}（缺失 {int(df['income_missing'].sum()):,} 条）")
    income_median = df["monthly_income"].median()
    df["monthly_income"] = df["monthly_income"].fillna(income_median)
    print(f"用于填充的 monthly_income 中位数：{income_median:,.2f}")
    print(f"清洗后：monthly_income 缺失率 {pct(miss_rate(df['monthly_income']))}")
    print(f"新增 income_missing，标记为 1 的占比 {pct(df['income_missing'].mean())}")

    # ---------------- 规则 6 ----------------
    line("规则 6：构造 5 个衍生字段")
    df["ever_90dpd"] = (df["n_90_dpd"] > 0).astype(int)
    df["ever_60dpd"] = (df["n_60_89_dpd"] > 0).astype(int)
    df["debt_per_line"] = df["debt_ratio"] / (df["open_credit_lines"] + 1)
    df["income_per_person"] = df["monthly_income"] / (df["n_dependents"] + 1)
    print(f"ever_90dpd     = (n_90_dpd > 0)              均值 {df['ever_90dpd'].mean():.4f}")
    print(f"ever_60dpd     = (n_60_89_dpd > 0)           均值 {df['ever_60dpd'].mean():.4f}")
    print(f"debt_per_line  = debt_ratio/(open_credit_lines+1)  缺失 {int(df['debt_per_line'].isna().sum()):,} 条")
    print(f"income_per_person = monthly_income/(n_dependents+1) 缺失 {int(df['income_per_person'].isna().sum()):,} 条")
    if df["income_per_person"].isna().any():
        n_dep_na = int(df["n_dependents"].isna().sum())
        print(f"  说明：缺失来自 n_dependents 原有缺失（{n_dep_na:,} 条），PROJECT.md 未规定其填充口径，故保留缺失。")
    print(f"当前形状：{df.shape[0]:,} 行 × {df.shape[1]} 列，新增特征 {len(NEW_FEATURES)} 个")

    line("清洗后缺失率总览")
    miss_tbl = pd.DataFrame({
        "缺失数": df.isna().sum(),
        "缺失率": df.isna().mean().round(6),
    })
    print(miss_tbl[miss_tbl["缺失数"] > 0].to_string() if miss_tbl["缺失数"].sum() else "所有字段无缺失")
    print(f"bad_flag 均值（整体坏账率）：{df['bad_flag'].mean():.4f}")

    # ---------------- 分箱 ----------------
    line("5 等频分箱（qcut, duplicates='drop'）+ 每箱 count / bad_rate")
    bin_frames = []
    for col in BIN_COLS:
        s = df[col]
        print(f"\n--- {col} ---")
        print(f"   取值：min={s.min():,.4f}  max={s.max():,.4f}  唯一值 {s.nunique():,} 个")
        try:
            binned = pd.qcut(s, q=5, duplicates="drop")
        except Exception as exc:  # 数据退化时给出明确原因
            print(f"   [WARN] {col} 分箱失败：{exc}")
            continue
        # 箱边界与每箱数量/坏账率
        grp = (
            df.groupby(binned, observed=True)
              .agg(count=("bad_flag", "size"), bad_rate=("bad_flag", "mean"))
              .reset_index()
              .rename(columns={col: "bin"})
        )
        n_bins = len(grp)
        print(f"   实际箱数：{n_bins}（duplicates='drop' 后）")
        if n_bins < 5:
            print(f"   [NOTE] 因取值高度重复，5 等分退化为 {n_bins} 箱")
        show = grp.copy()
        show["bin"] = show["bin"].astype(str)
        show["count"] = show["count"].astype(int)
        show["bad_rate"] = show["bad_rate"].round(4)
        print(show.to_string(index=False))
        for _, r in grp.iterrows():
            bin_frames.append({
                "variable": col,
                "bin": str(r["bin"]),
                "count": int(r["count"]),
                "bad_rate": round(float(r["bad_rate"]), 6),
            })

    bin_df = pd.DataFrame(bin_frames, columns=["variable", "bin", "count", "bad_rate"])

    # ---------------- before / after 对比（逐条对应清洗规则 1-6）----------------
    line("构造 clean_before_after.csv（逐条对应 PROJECT.md 清洗规则 1-6）")

    raw_dpd_over10 = sum(
        int((df_raw[c] > 10).sum())
        for c in ["NumberOfTime30-59DaysPastDueNotWorse",
                  "NumberOfTimes90DaysLate",
                  "NumberOfTime60-89DaysPastDueNotWorse"]
    )
    cur_dpd_over10 = sum(int((df[c] > 10).sum()) for c in DPD_COLS)

    ba_rows = [
        ("总样本数", f"{df_raw.shape[0]:,}", f"{df.shape[0]:,}"),
        ("总列数", f"{df_raw.shape[1]}", f"{df.shape[1]}"),
        ("规则1 - Unnamed: 0 列", "存在" if "Unnamed: 0" in df_raw.columns else "不存在", "已删除"),
        ("规则1 - 标签列名", "SeriousDlqin2yrs", "bad_flag"),
        ("规则2 - age <= 0 记录数",
         f"{int((df_raw['age'] <= 0).sum()):,}", f"{int((df['age'] <= 0).sum()):,}"),
        ("规则2 - age 最小值", f"{df_raw['age'].min():.0f}", f"{df['age'].min():.0f}"),
        ("规则2 - age 缺失率", pct(miss_rate(df_raw["age"])), pct(miss_rate(df["age"]))),
        ("规则3 - revolving_util 最大值",
         f"{df_raw['RevolvingUtilizationOfUnsecuredLines'].max():,.4f}",
         f"{df['revolving_util'].max():,.4f}"),
        ("规则3 - revolving_util > 1.0 记录数",
         f"{int((df_raw['RevolvingUtilizationOfUnsecuredLines'] > 1.0).sum()):,}",
         f"{int((df['revolving_util'] > 1.0).sum()):,}"),
        ("规则4 - 逾期字段 > 10 记录数", f"{raw_dpd_over10:,}", f"{cur_dpd_over10:,}"),
        ("规则4 - n_90_dpd 最大值",
         f"{df_raw['NumberOfTimes90DaysLate'].max():.0f}", f"{df['n_90_dpd'].max():.0f}"),
        ("规则5 - monthly_income 缺失率",
         pct(miss_rate(df_raw["MonthlyIncome"])), pct(miss_rate(df["monthly_income"]))),
        ("规则5 - income_missing 指示列", "不存在",
         f"已新增（=1 占 {pct(df['income_missing'].mean())}）"),
        ("规则6 - 新增衍生字段数", "0", f"{len(NEW_FEATURES)}"),
        ("bad_flag 均值（整体坏账率）",
         f"{df_raw['SeriousDlqin2yrs'].mean():.4f}", f"{df['bad_flag'].mean():.4f}"),
    ]
    ba = pd.DataFrame(ba_rows, columns=["指标", "清洗前", "清洗后"])
    print(ba.to_string(index=False))

    # ---------------- 落盘 ----------------
    line("写出文件（encoding='utf-8-sig'）")
    out_cleaned = BASE / "cleaned.csv"
    out_ba = BASE / "clean_before_after.csv"
    out_bin = BASE / "bin_bad_rate.csv"

    df.to_csv(out_cleaned, index=False, encoding="utf-8-sig")
    ba.to_csv(out_ba, index=False, encoding="utf-8-sig")
    bin_df.to_csv(out_bin, index=False, encoding="utf-8-sig")

    for p in (out_cleaned, out_ba, out_bin):
        print(f"已写入 {p.name:<26} {p.stat().st_size:>10,} 字节")

    # ---------------- 回读校验 + 打印前 5 行 ----------------
    line("校验：回读三个文件，打印行数与前 5 行")
    for p in (out_cleaned, out_ba, out_bin):
        back = pd.read_csv(p, encoding="utf-8-sig")
        print(f"\n>>> {p.name}：{back.shape[0]:,} 行 × {back.shape[1]} 列")
        head = back.head(5)
        print(head.to_string(index=False, max_colwidth=40))

    line("完成")
    print(f"输入行数={df_raw.shape[0]:,}  清洗后行数={df.shape[0]:,}  "
          f"cleaned.csv={pd.read_csv(out_cleaned, encoding='utf-8-sig').shape[0]:,} 行")
    print(f"bin_bad_rate.csv 共 {len(bin_df)} 行，覆盖变量：{sorted(bin_df['variable'].unique())}")


if __name__ == "__main__":
    main()
