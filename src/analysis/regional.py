"""H4: 지역·기관 편중 (Gini / 인구보정 / Local Moran's I).

입력
----
- claims : long-form (period, ingredient, region_code, claim_count, claim_amount)
- population : region_code, year, population

`pysal` 이 설치돼 있으면 Local Moran's I 도 계산, 없으면 건너뛴다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ._common import ensure_schema, to_year

logger = logging.getLogger(__name__)


@dataclass
class RegionalParams:
    min_amount: float = 5e9         # 50억 원 이상 약만
    hotspot_z: float = 3.0          # 시군구 z-score
    gini_threshold: float = 0.55    # Gini 임계
    min_hotspots: int = 2


def gini(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    if x.size == 0 or x.sum() == 0:
        return np.nan
    x = np.sort(x)
    n = x.size
    cum = np.cumsum(x)
    return (n + 1 - 2 * cum.sum() / cum[-1]) / n


def per_capita(
    claims: pd.DataFrame, population: pd.DataFrame
) -> pd.DataFrame:
    df = ensure_schema(
        claims, required=["period", "ingredient", "region_code", "claim_count", "claim_amount"]
    )
    df["year"] = to_year(df["period"])
    pop = population.rename(columns={"region_code": "region_code"})
    df = df.merge(pop, on=["region_code", "year"], how="left")
    df["claims_per_10k"] = df["claim_count"] / df["population"] * 10_000
    df["amount_per_capita"] = df["claim_amount"] / df["population"]
    return df


def detect(
    claims: pd.DataFrame,
    population: pd.DataFrame,
    params: RegionalParams | None = None,
) -> pd.DataFrame:
    params = params or RegionalParams()
    df = per_capita(claims, population)

    candidates = []
    for (year, ing), g in df.groupby(["year", "ingredient"], dropna=False):
        if g["claim_amount"].sum() < params.min_amount:
            continue
        per_cap = g["claims_per_10k"].dropna()
        if len(per_cap) < 10:
            continue
        z = (per_cap - per_cap.mean()) / per_cap.std(ddof=0)
        hotspot_mask = z >= params.hotspot_z
        hotspots = g.loc[per_cap[hotspot_mask].index, "region_code"].tolist()
        g_gini = gini(per_cap.values)
        if len(hotspots) >= params.min_hotspots and g_gini >= params.gini_threshold:
            candidates.append(
                {
                    "year": year,
                    "ingredient": ing,
                    "gini": g_gini,
                    "n_hotspots": len(hotspots),
                    "hotspots": ",".join(map(str, hotspots[:20])),
                    "total_amount": g["claim_amount"].sum(),
                    "max_z": float(z.max()),
                }
            )
    out = pd.DataFrame(candidates)
    if out.empty:
        return out
    out["score"] = out["gini"] * 10 + np.log1p(out["max_z"]) + np.log1p(out["total_amount"]) * 0.1
    return out.sort_values("score", ascending=False).reset_index(drop=True)


def local_morans_i(values: pd.Series, weights) -> pd.Series:
    """선택: pysal 가 있을 때만 사용."""
    try:
        from esda.moran import Moran_Local  # type: ignore
    except ImportError:
        logger.warning("esda 미설치 — Local Moran's I 건너뜀")
        return pd.Series(index=values.index, dtype=float)
    mi = Moran_Local(values.values, weights)
    return pd.Series(mi.Is, index=values.index)
