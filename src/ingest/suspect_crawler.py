"""의심 의약품 8종 묶음 A 트랙 크롤러.

`data/processed/suspect_drugs.json` 의 cmpnCd 들을 한꺼번에 cmpn_sick(상병별 시계열) 로 받는다.
콜린알포 choline_crawler 와 동일한 엔드포인트(`cmpn_sick`)·동일 구조이지만
대상 약물이 8종으로 확장된 게 다름.

사용:
  python -m src.select_suspect_drugs                  # 1) 8종 cmpnCd 추출
  python -m src.ingest.suspect_crawler --limit 8000   # 2) 시계열 수집

산출:
  data/processed/suspect_sick.parquet         (period × gnl_nm_cd × sick_cd 청구)
  data/processed/_suspect_progress.json       진척
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Iterable

import pandas as pd

from ..config import SETTINGS
from .hira_client import HiraClient

logger = logging.getLogger(__name__)

PROGRESS_FILE = "_suspect_progress.json"
DATA_FILE = "suspect_sick.parquet"
DRUGS_FILE = "suspect_drugs.json"

START_YM = 201501
END_YM = 202412


def year_months(start: int, end: int) -> Iterable[str]:
    y, m = divmod(start, 100)
    while y * 100 + m <= end:
        yield f"{y:04d}{m:02d}"
        m += 1
        if m > 12:
            y += 1
            m = 1


def load_targets() -> dict[str, list[str]]:
    """suspect_drugs.json → {label: [cmpnCd, ...]}"""
    p = SETTINGS.data_processed / DRUGS_FILE
    if not p.exists():
        raise FileNotFoundError(
            f"{p} 가 없다. 먼저 `python -m src.select_suspect_drugs` 실행."
        )
    raw = json.loads(p.read_text(encoding="utf-8"))
    return {
        label: [item["cmpn_cd"] for item in items]
        for label, items in raw.items()
        if items  # 빈 결과 제외
    }


def load_progress() -> set[tuple[str, str]]:
    p = SETTINGS.data_processed / PROGRESS_FILE
    if not p.exists():
        return set()
    return {tuple(t) for t in json.loads(p.read_text(encoding="utf-8"))}


def save_progress(done: set[tuple[str, str]]) -> None:
    SETTINGS.data_processed.mkdir(parents=True, exist_ok=True)
    (SETTINGS.data_processed / PROGRESS_FILE).write_text(
        json.dumps(sorted(done), ensure_ascii=False), encoding="utf-8"
    )


def _persist(rows: list[dict]) -> None:
    if not rows:
        return
    df = pd.DataFrame(rows)
    out = SETTINGS.data_processed / DATA_FILE
    if out.exists():
        existing = pd.read_parquet(out)
        df = pd.concat([existing, df], ignore_index=True).drop_duplicates(
            subset=["period", "gnl_nm_cd", "sick_cd"]
        )
    df.to_parquet(out, index=False)


def crawl(limit: int) -> None:
    client = HiraClient()
    targets = load_targets()
    done = load_progress()

    # 작업표 펼치기: (ym, cmpnCd) × drug_label
    all_pairs = []
    drug_lookup: dict[str, str] = {}
    for label, cmpn_list in targets.items():
        for cmpn in cmpn_list:
            drug_lookup[cmpn] = label

    total_pairs = 0
    for ym in year_months(START_YM, END_YM):
        for cmpn in drug_lookup:
            total_pairs += 1
            key = (ym, cmpn)
            if key not in done:
                all_pairs.append(key)

    logger.info(
        "약물 %d 종(콜린알포 포함), cmpnCd 총 %d 개, 작업 %d, 미완 %d (limit=%d)",
        len(targets), len(drug_lookup), total_pairs, len(all_pairs), limit,
    )

    rows: list[dict] = []
    n = 0
    started = time.time()
    try:
        for ym, cmpn in all_pairs:
            if n >= limit:
                logger.info("daily limit reached")
                break
            params = dict(
                diagYm=ym,
                gnlNmCd=cmpn,
                insupTp="4",
                cpmdPrscTp="01",
            )
            try:
                items = client.collect_all("cmpn_sick", params)
            except Exception as e:
                logger.warning("skip %s %s: %s", ym, cmpn, e)
                continue
            label = drug_lookup.get(cmpn, "")
            for it in items:
                rows.append(dict(
                    period=it.get("diagYm", ym),
                    gnl_nm_cd=it.get("gnlNmCd", cmpn),
                    gnl_nm_label=label,
                    sick_cd=it.get("st3SickSym"),
                    sick_name=it.get("st3SickSymNm"),
                    insup_tp=it.get("insupTpCd"),
                    claim_count=int(float(it.get("totUseQty") or 0)),
                    claim_amount=int(float(it.get("msupUseAmt") or 0)),
                ))
            done.add((ym, cmpn))
            n += 1
            save_progress(done)
            if n % 10 == 0:
                _persist(rows)
                rows = []
                logger.info(
                    "progress: %d this run, %.0fs elapsed, done=%d",
                    n, time.time() - started, len(done),
                )
    finally:
        save_progress(done)
        if rows:
            _persist(rows)
        logger.info("종료. 누적 done=%d, 이번 실행=%d", len(done), n)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=9000)
    args = p.parse_args()
    crawl(args.limit)


if __name__ == "__main__":
    main()
