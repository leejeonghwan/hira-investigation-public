"""1단계 → 2단계 브리지: 후보 약효 선정 + cmpnCd 작업표 생성.

워크플로우
---------
1. 1단계 결과(`macro_seoul_meft.parquet`)에 surge.detect 적용
2. score 상위 N 약효 추출 (기본 5)
3. 약제급여목록표에서 각 약효의 cmpnCd 리스트
4. 각 cmpnCd 의 약가마스터 정보 (가격, 등재일, 제조사) 미리 join
5. 핫스팟 시군구 (regional.detect 의 hotspots 컬럼) 상위 10개 선정
6. (cmpnCd × sgguCd × 120월) 작업표 저장 → cmpn_crawler 가 이걸 읽는다
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import pandas as pd

from .analysis import regional, surge
from .config import SETTINGS
from .ingest.reference_loader import load_give_list, load_price_master

logger = logging.getLogger(__name__)


def pick_top_meft(macro_df: pd.DataFrame, top_n: int = 5) -> pd.DataFrame:
    """surge.detect 로 상위 약효 N개 추출."""
    detected = surge.detect(macro_df, years=(2018, 2024))
    if detected.empty:
        # surge 임계 미달 시 단순 CAGR 기준
        yearly = surge.annualize(macro_df)
        growth = surge.compute_growth(yearly)
        latest = growth[growth["year"] == growth["year"].max()].copy()
        latest = latest.sort_values("cagr_5y", ascending=False, na_position="last")
        return latest.head(top_n)
    return detected.head(top_n)


def pick_hotspot_sggus(macro_df: pd.DataFrame, top_n: int = 10) -> list[str]:
    """1단계 데이터로 시군구 z-score 합산 상위 N개."""
    # 인구 보정 안 함 (단순 청구금액 z). 보정 가능하면 regional.detect 사용.
    by_sggu = (
        macro_df.groupby("region_code")["claim_amount"]
        .sum()
        .reset_index()
        .sort_values("claim_amount", ascending=False)
    )
    return by_sggu["region_code"].head(top_n).astype(str).tolist()


def build_task_table(
    candidates_meft: pd.DataFrame,
    sggus: list[str],
    give: pd.DataFrame,
    start_ym: int = 201501,
    end_ym: int = 202412,
) -> pd.DataFrame:
    """후보 약효 × 약효 안 cmpnCd × sggu × month 작업표."""
    rows = []
    for _, row in candidates_meft.iterrows():
        meft3 = str(row.get("atc_class") or row.get("meftDivNo") or "")[:3]
        cmpn_list = give[
            give["meft_div_no"].astype(str).str.startswith(meft3)
        ]["cmpn_cd"].dropna().unique().tolist()
        if not cmpn_list:
            logger.warning("no cmpn_cd for meft %s — give_list 누락 가능", meft3)
            continue
        for cmpn in cmpn_list:
            for sggu in sggus:
                for ym in _year_months(start_ym, end_ym):
                    rows.append((meft3, cmpn, sggu, ym))
    df = pd.DataFrame(rows, columns=["meft", "cmpn_cd", "sggu", "diag_ym"])
    return df


def _year_months(start: int, end: int):
    y, m = divmod(start, 100)
    while y * 100 + m <= end:
        yield f"{y:04d}{m:02d}"
        m += 1
        if m > 12:
            y += 1
            m = 1


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--top", type=int, default=5)
    p.add_argument("--sggu-top", type=int, default=10)
    args = p.parse_args()

    macro_path = SETTINGS.data_processed / "macro_seoul_meft.parquet"
    macro = pd.read_parquet(macro_path)
    logger.info("macro rows: %d, periods: %d", len(macro), macro["period"].nunique())

    candidates = pick_top_meft(macro, top_n=args.top)
    logger.info("top meft candidates:\n%s", candidates.head(args.top).to_string())

    hotspots = pick_hotspot_sggus(macro, top_n=args.sggu_top)
    logger.info("hotspot sggus: %s", hotspots)

    give = load_give_list()
    tasks = build_task_table(candidates, hotspots, give)
    out = SETTINGS.data_processed / "step2_tasks.parquet"
    tasks.to_parquet(out, index=False)
    out_csv = SETTINGS.data_processed / "step2_tasks.csv"
    tasks.to_csv(out_csv, index=False)
    logger.info("작업표 저장: %d tasks → %s", len(tasks), out)

    # 메타 정보 같이 저장
    meta = {
        "top_meft": candidates[["atc_class", "ingredient"]].to_dict(orient="records"),
        "hotspot_sggus": hotspots,
        "n_tasks": len(tasks),
        "est_days_at_9000_per_day": round(len(tasks) / 9000, 1),
    }
    (SETTINGS.data_processed / "step2_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
