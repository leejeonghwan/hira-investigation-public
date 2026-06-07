"""H3 실 스키마: 오리지널 vs 제네릭 잠재 절감액 추정.

전제
----
- 2단계 크롤로 성분 단위 청구금액(`step2_cmpn_area.parquet`) 보유
- 약가마스터 + 약제급여목록표 로 성분별 오리지널·제네릭 가격 분포 보유
- API 가 품목 단위 제공 안 함 → '오리지널 가격에 청구건이 일어났다고 가정한 시나리오' 와
  '제네릭 평균가에 청구건이 일어났다고 가정한 시나리오' 의 차액으로 잠재 절감액 추정

산출
----
- period × cmpn_cd: original_listed, generic_listed, brand_price, generic_price,
  price_gap_ratio, total_amount, savings_50pct, savings_70pct
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ._common import ensure_schema, to_year


@dataclass
class H3RealParams:
    min_years_since_generic: int = 5
    price_gap_threshold: float = 2.0  # 오리지널이 제네릭의 2배 이상 비쌈
    min_amount: float = 5e9  # 50억 원


def compute_price_ladder(give: pd.DataFrame) -> pd.DataFrame:
    """성분별: 오리지널 가격, 제네릭 평균 가격, 제네릭 등재 후 경과 연수."""
    g = give.dropna(subset=["listed_ym", "cmpn_cd", "price_upper"]).copy()
    g["listed_ym"] = g["listed_ym"].astype(str).str.slice(0, 6)
    g = g.sort_values("listed_ym")
    out_rows = []
    for cmpn, sub in g.groupby("cmpn_cd"):
        first = sub.iloc[0]
        rest = sub.iloc[1:]
        out_rows.append({
            "cmpn_cd": cmpn,
            "original_listed_ym": first["listed_ym"],
            "original_maker": first.get("maker"),
            "original_name": first.get("kor_name"),
            "brand_price": float(first["price_upper"]),
            "generic_listed_ym": rest["listed_ym"].iloc[0] if len(rest) else None,
            "generic_avg_price": float(rest["price_upper"].mean()) if len(rest) else np.nan,
            "n_items": int(sub["cmpn_cd"].size),
        })
    return pd.DataFrame(out_rows)


def detect(
    cmpn_claims: pd.DataFrame,
    give: pd.DataFrame,
    params: H3RealParams | None = None,
) -> pd.DataFrame:
    params = params or H3RealParams()
    df = ensure_schema(
        cmpn_claims,
        required=["period", "cmpn_cd", "claim_count", "claim_amount"],
    )
    df["year"] = to_year(df["period"])
    ladder = compute_price_ladder(give)

    yearly = (
        df.groupby(["year", "cmpn_cd"])
        .agg(total_amount=("claim_amount", "sum"), total_count=("claim_count", "sum"))
        .reset_index()
        .merge(ladder, on="cmpn_cd", how="left")
    )

    yearly["price_gap_ratio"] = yearly["brand_price"] / yearly["generic_avg_price"].replace(0, np.nan)
    yearly["years_since_generic"] = yearly["year"] - yearly["generic_listed_ym"].str.slice(0, 4).astype(float)

    # 시나리오: 오리지널 처방의 50%/70% 를 제네릭으로 대체했을 때 절감
    yearly["assumed_orig_count_at_brand_price"] = yearly["total_amount"] / yearly["brand_price"].replace(0, np.nan)
    yearly["savings_50pct"] = (
        yearly["assumed_orig_count_at_brand_price"] * (yearly["brand_price"] - yearly["generic_avg_price"]) * 0.5
    ).clip(lower=0)
    yearly["savings_70pct"] = (
        yearly["assumed_orig_count_at_brand_price"] * (yearly["brand_price"] - yearly["generic_avg_price"]) * 0.7
    ).clip(lower=0)

    flagged = yearly[
        (yearly["years_since_generic"] >= params.min_years_since_generic)
        & (yearly["price_gap_ratio"] >= params.price_gap_threshold)
        & (yearly["total_amount"] >= params.min_amount)
    ].copy()
    flagged = flagged.sort_values("savings_50pct", ascending=False).reset_index(drop=True)
    return flagged
