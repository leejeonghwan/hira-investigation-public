"""4개 분석 모듈을 한 번에 돌려 reports/tables 로 CSV 를 떨군다."""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd

from ..config import SETTINGS
from . import concentration, generic_vs_brand, regional, surge


def _load(path: Path) -> pd.DataFrame:
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    if path.suffix == ".csv":
        return pd.read_csv(path)
    raise ValueError(path)


def run(
    main_claims: Path,
    region_claims: Path | None = None,
    master: Path | None = None,
    population: Path | None = None,
) -> None:
    SETTINGS.reports_tables.mkdir(parents=True, exist_ok=True)
    claims = _load(main_claims)

    logging.info("H1 surge")
    surge_out = surge.detect(claims)
    surge_out.to_csv(SETTINGS.reports_tables / "h1_surge.csv", index=False)

    if "maker" in claims.columns:
        logging.info("H2 concentration")
        conc_out = concentration.detect(claims)
        conc_out.to_csv(SETTINGS.reports_tables / "h2_concentration.csv", index=False)

    if master and master.exists() and "item_seq" in claims.columns:
        logging.info("H3 generic_vs_brand")
        master_df = _load(master)
        brand_out = generic_vs_brand.detect(claims, master_df)
        brand_out.to_csv(SETTINGS.reports_tables / "h3_brand_vs_generic.csv", index=False)

    if region_claims and region_claims.exists() and population and population.exists():
        logging.info("H4 regional")
        reg_df = _load(region_claims)
        pop_df = _load(population)
        reg_out = regional.detect(reg_df, pop_df)
        reg_out.to_csv(SETTINGS.reports_tables / "h4_regional.csv", index=False)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--main", required=True, type=Path)
    p.add_argument("--region", type=Path)
    p.add_argument("--master", type=Path)
    p.add_argument("--population", type=Path)
    args = p.parse_args()
    run(args.main, args.region, args.master, args.population)


if __name__ == "__main__":
    main()
