"""10년치 의약품 사용통계를 수집해 parquet 으로 떨어뜨리는 오케스트레이션."""
from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Iterable

import pandas as pd

from ..config import SETTINGS
from .hira_client import HiraClient

logger = logging.getLogger(__name__)


def year_months(start_year: int, end_year: int) -> Iterable[str]:
    for y in range(start_year, end_year + 1):
        for m in range(1, 13):
            yield f"{y}{m:02d}"


def fetch_monthly(
    client: HiraClient,
    endpoint: str,
    start_year: int,
    end_year: int,
    extra_params: dict | None = None,
    period_key: str = "stdYm",
) -> pd.DataFrame:
    """월 단위 통계를 수집해 하나의 DataFrame 으로 합친다."""
    frames = []
    extra_params = extra_params or {}
    for ym in year_months(start_year, end_year):
        params = {period_key: ym, **extra_params}
        rows = client.collect_all(endpoint, params)
        if not rows:
            continue
        df = pd.DataFrame(rows)
        df["__period"] = ym
        df["__endpoint"] = endpoint
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def write_parquet(df: pd.DataFrame, name: str) -> Path:
    SETTINGS.data_processed.mkdir(parents=True, exist_ok=True)
    out = SETTINGS.data_processed / f"{name}.parquet"
    df.to_parquet(out, index=False)
    logger.info("wrote %s rows -> %s", len(df), out)
    return out


def run(start_year: int, end_year: int, endpoints: list[str]) -> None:
    client = HiraClient()
    for ep in endpoints:
        df = fetch_monthly(client, ep, start_year, end_year)
        if df.empty:
            logger.warning("no data for %s", ep)
            continue
        write_parquet(df, ep)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=2015)
    parser.add_argument("--end", type=int, default=2024)
    parser.add_argument(
        "--endpoints",
        nargs="+",
        default=[
            "mdcn_usage_by_main",
            "mdcn_usage_by_ingredient",
            "mdcn_usage_by_region",
            "mdcn_usage_by_instkind",
        ],
    )
    args = parser.parse_args()
    run(args.start, args.end, args.endpoints)


if __name__ == "__main__":
    main()
