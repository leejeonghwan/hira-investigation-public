"""H2: 고가 의약품 청구 집중도 (HHI / Top-1 / 건당 단가).

입력 DataFrame 기대 컬럼:
- period, atc_class, ingredient, maker, claim_count, claim_amount

`maker` 가 비어 있으면 약가마스터 조인을 먼저 해야 한다.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ._common import ensure_schema, to_year


@dataclass
class ConcentrationParams:
    hhi_threshold: int = 2500          # 미국 반독점 기준
    top1_threshold: float = 0.50       # Top-1 점유 50%
    unit_cost_percentile: float = 0.95  # 건당단가 상위 5%


def compute(df: pd.DataFrame) -> pd.DataFrame:
    df = ensure_schema(df, required=["period", "atc_class", "claim_count", "claim_amount", "maker"])
    df["year"] = to_year(df["period"])

    # 약효분류 × 제조사 × 연도 집계
    by_maker = (
        df.groupby(["year", "atc_class", "maker"], dropna=False)
        .agg(amount=("claim_amount", "sum"), count=("claim_count", "sum"))
        .reset_index()
    )

    # 약효분류 × 연도 총합
    class_total = (
        by_maker.groupby(["year", "atc_class"], dropna=False)["amount"]
        .sum()
        .rename("class_amount")
        .reset_index()
    )
    by_maker = by_maker.merge(class_total, on=["year", "atc_class"], how="left")
    by_maker["share"] = by_maker["amount"] / by_maker["class_amount"]

    # HHI
    hhi = (
        by_maker.assign(sq=lambda d: (d["share"] * 100) ** 2)
        .groupby(["year", "atc_class"])["sq"]
        .sum()
        .rename("hhi")
        .reset_index()
    )
    top1 = (
        by_maker.sort_values("share", ascending=False)
        .groupby(["year", "atc_class"])
        .head(1)[["year", "atc_class", "maker", "share"]]
        .rename(columns={"maker": "top1_maker", "share": "top1_share"})
    )
    top3 = (
        by_maker.sort_values("share", ascending=False)
        .groupby(["year", "atc_class"])
        .head(3)
        .groupby(["year", "atc_class"])["share"]
        .sum()
        .rename("top3_share")
        .reset_index()
    )

    # 건당 단가 (전체 약효분류 평균)
    unit = (
        by_maker.groupby(["year", "atc_class"])
        .agg(amount=("amount", "sum"), count=("count", "sum"))
        .assign(unit_cost=lambda d: d["amount"] / d["count"].replace(0, np.nan))
        .reset_index()[["year", "atc_class", "unit_cost"]]
    )

    out = hhi.merge(top1, on=["year", "atc_class"], how="left")
    out = out.merge(top3, on=["year", "atc_class"], how="left")
    out = out.merge(unit, on=["year", "atc_class"], how="left")
    out = out.merge(class_total, on=["year", "atc_class"], how="left")
    return out


def detect(df: pd.DataFrame, params: ConcentrationParams | None = None) -> pd.DataFrame:
    params = params or ConcentrationParams()
    metrics = compute(df)
    cutoff = metrics["unit_cost"].quantile(params.unit_cost_percentile)
    flagged = metrics[
        (metrics["hhi"] >= params.hhi_threshold)
        & (metrics["top1_share"] >= params.top1_threshold)
        & (metrics["unit_cost"] >= cutoff)
    ].copy()
    flagged["score"] = (
        flagged["hhi"] / 100 + flagged["top1_share"] * 50 + np.log1p(flagged["class_amount"]) * 0.1
    )
    return flagged.sort_values(["year", "score"], ascending=[False, False]).reset_index(drop=True)
