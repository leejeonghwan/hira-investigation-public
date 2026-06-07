"""H5: 의원-병원 오리지널 점유율 격차 (G 패턴, 유착 정황 시그널).

가설
----
같은 성분에 동등 효과·저가 제네릭이 충분히 있는데도, 의원(31) 의 오리지널 처방 점유율이
종합병원(11)·상급종합(01) 보다 유의미하게 높다면, 의학적으로 설명되지 않는다.
가능한 설명: (a) 제약사 영업·리베이트 (b) 학회·교육 의존 (c) 종합병원 처방 답습.

입력
----
step3_cmpn_cl.parquet  : period, cmpn_cd, region_code, cl_cd, claim_amount, claim_count
price_master            : cmpn_cd, item_seq, maker, auth_date, kor_name
give                    : cmpn_cd, listed_ym, maker, kor_name, price_upper, n_items

산출 (성분 × 연 단위)
- clinic_brand_share, hospital_brand_share, gap_pp (의원-병원), z, p_value (chi-sq)
- original_maker (단정 가능한 회사), n_generic_items
- assumed_excess_amount (의원 오리지널 점유가 병원 수준이었다면 얼마 덜 썼나)

해석상 주의
- 격차가 크다 = 의심 정황. 단정 보도 X. 전문가 인터뷰 + 회사 입장 + 공정위 이력 교차검증 필수.
- 의원/병원 환자군 자체가 다를 수 있음 (의원=경증, 병원=중증). 같은 진단명 안에서 비교가 정석.
  (현 데이터엔 진단명 차원이 없어 1차 시그널로만.)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ._common import ensure_schema, to_year


@dataclass
class H5Params:
    min_amount: float = 1e9   # 10억 원 미만 성분은 노이즈
    min_gap_pp: float = 10.0  # 의원-병원 격차 10%p 이상
    gap_z_threshold: float = 2.0


def compute_brand_position(price_master: pd.DataFrame) -> pd.DataFrame:
    m = price_master.dropna(subset=["cmpn_cd", "auth_date"]).sort_values("auth_date")
    first = m.groupby("cmpn_cd").first()[["item_seq", "maker", "kor_name", "auth_date"]]
    first = first.rename(columns={
        "item_seq": "original_item",
        "maker": "original_maker",
        "kor_name": "original_name",
        "auth_date": "original_authd",
    }).reset_index()
    n_items = m.groupby("cmpn_cd").size().rename("n_items_total").reset_index()
    return first.merge(n_items, on="cmpn_cd", how="left")


def _join_brand_flag(cmpn_cl: pd.DataFrame, price_master: pd.DataFrame) -> pd.DataFrame:
    """API 가 성분 단위라 '오리지널 청구금액'은 직접 안 나옴.
    대신 '오리지널 가격 기준 추정 청구건수' = 청구금액 / 오리지널가 로 근사.
    좀 더 보수적으로 '청구금액 / 평균가' 도 같이 둔다. (give 가 있으면 더 정확)
    """
    return cmpn_cl  # 아래 detect 에서 가격 join


def detect(
    cmpn_cl: pd.DataFrame,
    price_master: pd.DataFrame,
    give: pd.DataFrame | None = None,
    params: H5Params | None = None,
) -> pd.DataFrame:
    params = params or H5Params()
    df = ensure_schema(
        cmpn_cl,
        required=["period", "cmpn_cd", "cl_cd", "claim_count", "claim_amount"],
    )
    df["year"] = to_year(df["period"])

    # 종별 그룹: 의원 vs 병원(상급종합 + 종합)
    df["cl_group"] = df["cl_cd"].map({"31": "clinic", "01": "hospital", "11": "hospital"})
    df = df[df["cl_group"].notna()].copy()

    # 연 × 성분 × 그룹별 청구금액·건수 합계
    agg = (
        df.groupby(["year", "cmpn_cd", "cl_group"])
        .agg(amount=("claim_amount", "sum"), count=("claim_count", "sum"))
        .reset_index()
    )

    # 오리지널 가격으로 환산: 청구금액 / 오리지널가 = "오리지널 가격 단가로 환산한 건수"
    # 진짜 처방건수(count) 와 비교해 환산건수가 많다면 = 비싼 약(=오리지널) 위주.
    brand = compute_brand_position(price_master)
    if give is not None and not give.empty:
        # 평균 제네릭 가격 추가
        g_long = give.dropna(subset=["cmpn_cd", "price_upper", "listed_ym"]).sort_values("listed_ym")
        first_idx = g_long.drop_duplicates("cmpn_cd", keep="first").set_index("cmpn_cd")["price_upper"]
        avg_gen = (
            g_long.groupby("cmpn_cd")
            .apply(lambda g: g["price_upper"].iloc[1:].mean() if len(g) > 1 else np.nan,
                   include_groups=False)
            .rename("generic_avg_price")
            .reset_index()
        )
        brand = brand.merge(
            first_idx.rename("brand_price").reset_index(),
            on="cmpn_cd", how="left",
        ).merge(avg_gen, on="cmpn_cd", how="left")
    else:
        brand["brand_price"] = np.nan
        brand["generic_avg_price"] = np.nan

    agg = agg.merge(brand, on="cmpn_cd", how="left")
    agg["unit_cost"] = agg["amount"] / agg["count"].replace(0, np.nan)

    # "오리지널 점유율 근사" = (unit_cost - 제네릭평균가) / (오리지널가 - 제네릭평균가)
    # 범위 [0,1] 로 클리핑. NaN(가격 정보 없음) 은 NaN 유지.
    span = (agg["brand_price"] - agg["generic_avg_price"]).replace(0, np.nan)
    agg["brand_share_proxy"] = ((agg["unit_cost"] - agg["generic_avg_price"]) / span).clip(0, 1)

    # 의원 vs 병원 격차 (성분 × 연도)
    pivot = (
        agg.pivot_table(
            index=["year", "cmpn_cd", "original_maker", "original_name", "brand_price",
                   "generic_avg_price", "n_items_total"],
            columns="cl_group",
            values=["brand_share_proxy", "amount", "count"],
        )
        .reset_index()
    )
    pivot.columns = [
        "_".join(c).strip("_") if isinstance(c, tuple) else c for c in pivot.columns
    ]
    pivot["gap_pp"] = (
        pivot.get("brand_share_proxy_clinic", np.nan)
        - pivot.get("brand_share_proxy_hospital", np.nan)
    ) * 100
    pivot["total_amount"] = (
        pivot.get("amount_clinic", 0).fillna(0) + pivot.get("amount_hospital", 0).fillna(0)
    )

    # "병원 수준으로 의원이 처방했다면 줄였을 금액" 추정
    pivot["assumed_excess_amount"] = (
        (pivot.get("brand_share_proxy_clinic", 0) - pivot.get("brand_share_proxy_hospital", 0))
        * (pivot.get("brand_price", 0) - pivot.get("generic_avg_price", 0))
        * pivot.get("count_clinic", 0).fillna(0)
    ).clip(lower=0)

    # 1차 후보 필터
    flagged = pivot[
        (pivot["total_amount"] >= params.min_amount)
        & (pivot["gap_pp"] >= params.min_gap_pp)
    ].copy()

    # 격차 z-score (성분 분포 안에서)
    flagged["gap_z"] = (
        flagged.groupby("year")["gap_pp"].transform(
            lambda x: (x - x.mean()) / x.std(ddof=0) if x.std(ddof=0) else 0
        )
    )

    flagged = flagged.sort_values(
        ["year", "assumed_excess_amount"], ascending=[False, False]
    ).reset_index(drop=True)
    return flagged
