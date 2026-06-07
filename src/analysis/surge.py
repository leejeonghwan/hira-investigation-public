"""H1: 처방량·청구액 급증 의약품 탐지.

입력
----
long-form DataFrame: period, atc_class, ingredient, claim_count, claim_amount

산출
----
성분 × 연도 단위로 다음을 계산해 1차 후보를 추출:
- yoy        : 전년 대비 청구금액 성장률
- cagr_5y    : 5년 CAGR
- class_z    : 같은 약효분류 내 yoy 의 표준점수
- abs_amount : 당해 청구금액

기본 임계값: class_z ≥ 2.0, cagr_5y ≥ 0.30, abs_amount ≥ 1e10 (100억).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ._common import ensure_schema, safe_zscore, to_year


@dataclass
class SurgeParams:
    # 같은 약효분류 내 성분이 적을수록 z 의 상한이 낮아진다(N=4 일 땐 ~1.73이 최대).
    # 1.5 는 한쪽으로 쏠린 분포에서도 안정적으로 잡히는 보수적 기준치.
    z_threshold: float = 1.5
    cagr_threshold: float = 0.30
    min_amount: float = 1e10  # 100억 원


def annualize(df: pd.DataFrame) -> pd.DataFrame:
    df = ensure_schema(df)
    df["year"] = to_year(df["period"])
    yearly = (
        df.groupby(["year", "atc_class", "ingredient"], dropna=False)
        .agg(claim_count=("claim_count", "sum"), claim_amount=("claim_amount", "sum"))
        .reset_index()
    )
    return yearly


def compute_growth(yearly: pd.DataFrame) -> pd.DataFrame:
    yearly = yearly.sort_values(["atc_class", "ingredient", "year"]).copy()
    grp = yearly.groupby(["atc_class", "ingredient"])
    yearly["amount_lag1"] = grp["claim_amount"].shift(1)
    yearly["amount_lag5"] = grp["claim_amount"].shift(5)
    yearly["yoy"] = yearly["claim_amount"] / yearly["amount_lag1"] - 1
    with np.errstate(invalid="ignore", divide="ignore"):
        yearly["cagr_5y"] = (yearly["claim_amount"] / yearly["amount_lag5"]) ** (1 / 5) - 1
    return yearly


def add_class_z(yearly: pd.DataFrame) -> pd.DataFrame:
    yearly = yearly.copy()
    yearly["class_z"] = (
        yearly.groupby(["year", "atc_class"])["yoy"].transform(safe_zscore)
    )
    return yearly


def detect(
    df: pd.DataFrame,
    params: SurgeParams | None = None,
    years: tuple[int, int] | None = None,
) -> pd.DataFrame:
    params = params or SurgeParams()
    yearly = compute_growth(annualize(df))
    yearly = add_class_z(yearly)
    if years:
        yearly = yearly[(yearly["year"] >= years[0]) & (yearly["year"] <= years[1])]
    flagged = yearly[
        (yearly["class_z"] >= params.z_threshold)
        & (yearly["cagr_5y"] >= params.cagr_threshold)
        & (yearly["claim_amount"] >= params.min_amount)
    ].copy()
    flagged["score"] = (
        flagged["class_z"].fillna(0) * 0.5
        + flagged["cagr_5y"].fillna(0) * 5
        + np.log1p(flagged["claim_amount"]) * 0.05
    )
    return flagged.sort_values("score", ascending=False).reset_index(drop=True)
