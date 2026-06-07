"""H2 실 스키마: 성분 안 오리지널 점유율 + 시장 집중도.

API 가 성분 단위까지만 제공하므로 회사별 점유율은 직접 못 계산한다.
대신 "성분 청구금액 안에서 오리지널 품목의 비중" 으로 회사별 점유 단서를 만든다.

입력
----
- step2_cmpn_area.parquet  : period, cmpn_cd, region_code, claim_amount, claim_count
- price_master            : cmpn_cd, item_seq, maker, auth_date, price_upper
- give_list               : cmpn_cd, listed_ym, meft_div_no
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ._common import ensure_schema, to_year


@dataclass
class H2RealParams:
    min_annual_amount: float = 1e10   # 100억 원
    original_share_threshold: float = 0.50
    top1_inferred_threshold: float = 0.30  # 오리지널 또는 단일 제네릭 비중


def compute_original_position(price_master: pd.DataFrame) -> pd.DataFrame:
    """성분코드별 오리지널(최초 허가) 품목·제조사 식별."""
    m = price_master.dropna(subset=["cmpn_cd", "auth_date"]).copy()
    m = m.sort_values("auth_date")
    first = (
        m.groupby("cmpn_cd")
        .first()[["item_seq", "maker", "kor_name", "auth_date"]]
        .reset_index()
        .rename(columns={
            "item_seq": "original_item",
            "maker": "original_maker",
            "kor_name": "original_name",
            "auth_date": "original_authd",
        })
    )
    # 같은 성분 내 등재 품목 수 (제네릭 다양성 지표)
    counts = m.groupby("cmpn_cd").size().rename("n_items_total").reset_index()
    first = first.merge(counts, on="cmpn_cd", how="left")
    return first


def detect(
    cmpn_claims: pd.DataFrame,
    price_master: pd.DataFrame,
    params: H2RealParams | None = None,
) -> pd.DataFrame:
    """성분-연 단위로 오리지널 점유 + 시장 집중도 시그널 추출."""
    params = params or H2RealParams()
    df = ensure_schema(
        cmpn_claims,
        required=["period", "cmpn_cd", "claim_count", "claim_amount"],
    )
    df["year"] = to_year(df["period"])

    yearly = (
        df.groupby(["year", "cmpn_cd"])
        .agg(claim_amount=("claim_amount", "sum"), claim_count=("claim_count", "sum"))
        .reset_index()
    )

    orig = compute_original_position(price_master)
    out = yearly.merge(orig, on="cmpn_cd", how="left")
    # 큰 성분만 후보로
    out = out[out["claim_amount"] >= params.min_annual_amount].copy()
    out["unit_cost"] = out["claim_amount"] / out["claim_count"].replace(0, np.nan)

    out = out.sort_values(["year", "claim_amount"], ascending=[True, False]).reset_index(drop=True)
    return out
