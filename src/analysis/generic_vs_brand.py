"""H3: 제네릭 대비 오리지널 과처방 + 잠재 절감액 추정.

전제: 처방 데이터에 'item_seq' 또는 'maker' 가 있어, 약가마스터에서
generic_flag (오리지널/제네릭) 와 price_upper 를 조인할 수 있어야 한다.

산출 컬럼:
- ingredient, year, original_share, generic_avg_price, brand_avg_price,
- price_gap_ratio, potential_savings, years_since_generic
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ._common import ensure_schema, to_year


@dataclass
class BrandParams:
    min_years_since_generic: int = 5
    original_share_threshold: float = 0.60
    price_gap_threshold: float = 2.0  # 오리지널이 제네릭의 2배 이상 비쌈
    min_amount: float = 5e9  # 50억 원


def join_master(claims: pd.DataFrame, master: pd.DataFrame) -> pd.DataFrame:
    """claims (성분/품목 단위 청구) 와 약가마스터를 조인.

    master 는 reference_loader.load_drug_price_master 가 만들어주는 스키마.
    """
    needed_master = {"item_seq", "ingredient_code", "maker", "price_upper", "first_listed"}
    missing = needed_master - set(master.columns)
    if missing:
        raise ValueError(f"master missing: {missing}")

    df = claims.copy()
    # claims 측 컬럼과 충돌 방지: 마스터에서 가져올 컬럼은 'item_seq' 만 키로 두고
    # 나머지는 접미사로 구분 후 필요한 것만 채택.
    master_cols = ["item_seq", "ingredient_code", "maker", "price_upper", "first_listed", "kor_name"]
    drop_from_claims = [c for c in master_cols if c in df.columns and c != "item_seq"]
    df = df.drop(columns=drop_from_claims).merge(
        master[master_cols], on="item_seq", how="left"
    )
    # 오리지널 판별: 같은 성분코드 중 최초 등재 품목
    first_per_ing = (
        master.dropna(subset=["first_listed"])
        .sort_values("first_listed")
        .groupby("ingredient_code")
        .first()[["item_seq", "first_listed"]]
        .rename(columns={"item_seq": "original_item_seq", "first_listed": "original_listed"})
        .reset_index()
    )
    df = df.merge(first_per_ing, on="ingredient_code", how="left")
    df["is_original"] = df["item_seq"] == df["original_item_seq"]
    return df


def detect(claims: pd.DataFrame, master: pd.DataFrame, params: BrandParams | None = None) -> pd.DataFrame:
    params = params or BrandParams()
    df = ensure_schema(
        claims,
        required=["period", "ingredient", "claim_count", "claim_amount", "item_seq"],
    )
    df["year"] = to_year(df["period"])
    df = join_master(df, master)

    # 제네릭 등재 시점: 한 성분에 오리지널 이후 첫 추가 품목 등재일
    generic_listed = (
        master.dropna(subset=["first_listed"])
        .sort_values("first_listed")
        .groupby("ingredient_code")
        .nth(1)[["ingredient_code", "first_listed"]]
        .rename(columns={"first_listed": "first_generic_listed"})
    )
    df = df.merge(generic_listed, on="ingredient_code", how="left")
    df["years_since_generic"] = (
        df["year"] - pd.to_datetime(df["first_generic_listed"]).dt.year
    )

    by_year_ing = (
        df.groupby(["year", "ingredient_code", "ingredient"], dropna=False)
        .apply(
            lambda g: pd.Series(
                {
                    "total_amount": g["claim_amount"].sum(),
                    "total_count": g["claim_count"].sum(),
                    "original_amount": g.loc[g["is_original"], "claim_amount"].sum(),
                    "original_count": g.loc[g["is_original"], "claim_count"].sum(),
                    "brand_avg_price": g.loc[g["is_original"], "price_upper"].mean(),
                    "generic_avg_price": g.loc[~g["is_original"], "price_upper"].mean(),
                    "years_since_generic": g["years_since_generic"].max(),
                }
            ),
            include_groups=False,
        )
        .reset_index()
    )

    by_year_ing["original_share"] = (
        by_year_ing["original_amount"] / by_year_ing["total_amount"].replace(0, np.nan)
    )
    by_year_ing["price_gap_ratio"] = (
        by_year_ing["brand_avg_price"] / by_year_ing["generic_avg_price"].replace(0, np.nan)
    )
    # 보수적 시나리오: 오리지널 처방의 50%를 제네릭으로 대체했다고 가정한 절감액
    by_year_ing["potential_savings"] = (
        by_year_ing["original_count"]
        * (by_year_ing["brand_avg_price"] - by_year_ing["generic_avg_price"])
        * 0.5
    ).clip(lower=0)

    flagged = by_year_ing[
        (by_year_ing["years_since_generic"] >= params.min_years_since_generic)
        & (by_year_ing["original_share"] >= params.original_share_threshold)
        & (by_year_ing["price_gap_ratio"] >= params.price_gap_threshold)
        & (by_year_ing["total_amount"] >= params.min_amount)
    ].copy()
    flagged = flagged.sort_values("potential_savings", ascending=False).reset_index(drop=True)
    return flagged
