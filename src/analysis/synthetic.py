"""실제 API 키 없이도 파이프라인을 돌려볼 수 있게 가짜 데이터셋을 만든다.

10년치 (2015~2024) 약효분류 × 성분 × 시군구 × 제조사 × 월 단위 청구 데이터를
임의로 생성하되, 일부 성분에 '이상치' 패턴(급증/집중/오리지널 과처방/지역 핫스팟)
을 의도적으로 심어둔다. analysis 모듈 단위 테스트용.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


ATC_CLASSES = ["A02BC", "C09AA", "C10AA", "J01CR", "L01XE", "N02BE", "N05BA", "M01AE"]
SEED = 42


@dataclass
class SyntheticOptions:
    start_year: int = 2015
    end_year: int = 2024
    n_ingredients_per_class: int = 6
    n_makers_per_ingredient: int = 3
    n_regions: int = 30


def _ingredient_id(atc: str, idx: int) -> str:
    return f"{atc}-ING{idx:02d}"


def make_claims(opts: SyntheticOptions | None = None) -> pd.DataFrame:
    opts = opts or SyntheticOptions()
    rng = np.random.default_rng(SEED)
    rows = []
    regions = [f"{11000 + i:05d}" for i in range(opts.n_regions)]
    years = list(range(opts.start_year, opts.end_year + 1))

    for atc in ATC_CLASSES:
        for ing_idx in range(opts.n_ingredients_per_class):
            ingredient = _ingredient_id(atc, ing_idx)
            base = rng.lognormal(mean=21, sigma=1.0)  # 연 청구금액 base (~1e9~1e10 scale)
            for maker_idx in range(opts.n_makers_per_ingredient):
                maker = f"{atc}-MAKER{maker_idx:02d}"
                # 첫 maker 를 '오리지널' 로 가정, 비싸게
                is_original = maker_idx == 0
                price_factor = 3.0 if is_original else 1.0
                share = 0.7 if is_original else 0.3 / (opts.n_makers_per_ingredient - 1)
                for year in years:
                    growth = 1 + rng.normal(0.03, 0.05)
                    amount = base * share * price_factor * (growth ** (year - opts.start_year))
                    for region in regions:
                        region_factor = rng.lognormal(0, 0.6) / opts.n_regions
                        rows.append(
                            dict(
                                period=str(year),
                                atc_class=atc,
                                ingredient=ingredient,
                                ingredient_code=ingredient,
                                item_seq=f"{ingredient}-{maker}",
                                maker=maker,
                                region_code=region,
                                inst_kind="의원",
                                claim_count=max(1, int(amount * region_factor / (1000 * price_factor))),
                                claim_amount=float(amount * region_factor),
                            )
                        )

    df = pd.DataFrame(rows)

    # === 이상치 주입 ===
    # 1) 급증: A02BC-ING01 가 2021년부터 매년 60% 성장
    mask = (df["ingredient"] == "A02BC-ING01") & (df["period"].astype(int) >= 2021)
    df.loc[mask, "claim_amount"] *= (
        1.6 ** (df.loc[mask, "period"].astype(int) - 2020)
    )

    # 2) 집중도: L01XE 전체에서 maker00 가 90% 점유
    mask = df["atc_class"] == "L01XE"
    df.loc[mask & (df["maker"] != "L01XE-MAKER00"), "claim_amount"] *= 0.1

    # 3) 오리지널 과처방: C10AA-ING00 의 오리지널 점유율을 80% 로 유지 + 가격차 큼 (위 price_factor 3배가 그 역할)

    # 4) 지역 편중: N05BA-ING02 가 region 11000~11004 에 5배 쏠림
    mask = (df["ingredient"] == "N05BA-ING02") & (df["region_code"].isin(regions[:5]))
    df.loc[mask, "claim_count"] *= 5
    df.loc[mask, "claim_amount"] *= 5

    return df


def make_master(claims: pd.DataFrame) -> pd.DataFrame:
    """위 claims 와 정합되는 약가마스터를 만든다."""
    uniq = claims[["item_seq", "ingredient_code", "maker"]].drop_duplicates()
    rng = np.random.default_rng(SEED + 1)

    def is_original(row: pd.Series) -> bool:
        return row["maker"].endswith("MAKER00")

    uniq["kor_name"] = uniq["item_seq"]
    uniq["price_upper"] = uniq.apply(
        lambda r: float(rng.uniform(2000, 5000) if is_original(r) else rng.uniform(500, 1500)),
        axis=1,
    )
    uniq["first_listed"] = uniq.apply(
        lambda r: pd.Timestamp("2005-01-01") if is_original(r) else pd.Timestamp("2012-01-01"),
        axis=1,
    )
    uniq["atc_code"] = uniq["ingredient_code"].str[:5]
    return uniq


def make_population(claims: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(SEED + 2)
    regions = claims["region_code"].unique()
    years = sorted(claims["period"].astype(int).unique())
    rows = []
    for r in regions:
        base = int(rng.uniform(50_000, 500_000))
        for y in years:
            rows.append(dict(region_code=r, year=y, population=base))
    return pd.DataFrame(rows)


def write_all(out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    claims = make_claims()
    master = make_master(claims)
    pop = make_population(claims)
    paths = {
        "claims": out_dir / "synthetic_claims.parquet",
        "master": out_dir / "synthetic_master.parquet",
        "population": out_dir / "synthetic_population.parquet",
    }
    claims.to_parquet(paths["claims"], index=False)
    master.to_parquet(paths["master"], index=False)
    pop.to_parquet(paths["population"], index=False)
    return paths


if __name__ == "__main__":
    import sys

    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/processed")
    print(write_all(out))
