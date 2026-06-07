"""분석 모듈 공통 헬퍼."""
from __future__ import annotations

import numpy as np
import pandas as pd

# 분석 단계에서 기대하는 컬럼 스키마
# - period         : 'YYYY' 또는 'YYYYMM'
# - atc_class      : 약효분류코드 (예: 'A02BC' for PPI)
# - ingredient     : 주성분코드 또는 성분명
# - maker          : 제조사 (약가마스터 조인 후에만 채워짐)
# - region_code    : 시군구 5자리 (없으면 NaN)
# - inst_kind      : 요양기관 종별 (없으면 NaN)
# - claim_count    : 청구건수
# - claim_amount   : 청구금액 (원)
# - dosage_unit    : (선택) 환산 사용량


REQUIRED_COLS = [
    "period",
    "atc_class",
    "ingredient",
    "claim_count",
    "claim_amount",
]


def ensure_schema(df: pd.DataFrame, required: list[str] = REQUIRED_COLS) -> pd.DataFrame:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"missing columns: {missing}. got: {list(df.columns)}")
    df = df.copy()
    df["claim_count"] = pd.to_numeric(df["claim_count"], errors="coerce").fillna(0)
    df["claim_amount"] = pd.to_numeric(df["claim_amount"], errors="coerce").fillna(0)
    df["period"] = df["period"].astype(str)
    return df


def to_year(period: pd.Series) -> pd.Series:
    return period.astype(str).str[:4].astype(int)


def safe_zscore(x: pd.Series) -> pd.Series:
    sd = x.std(ddof=0)
    if not sd or np.isnan(sd):
        return pd.Series(np.zeros(len(x)), index=x.index)
    return (x - x.mean()) / sd
