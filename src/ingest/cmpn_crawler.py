"""2단계 성분별 크롤러.

select_candidates.py 가 만들어 둔 `step2_tasks.parquet` 을 읽어,
`getCmpnAreaList1.2` 로 (cmpnCd × sgguCd × diagYm) 시계열을 수집.

호출 단위는 1단계와 동일: 한 번에 1행. 결과 컬럼은 성분 기준으로 다르다
(meftDivNo 대신 cmpnCd / cmpnCdNm).

사용
----
    python -m src.ingest.cmpn_crawler           # 오늘 9,000콜
    python -m src.ingest.cmpn_crawler --limit 200
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

import pandas as pd

from ..config import SETTINGS
from .hira_client import HiraClient

logger = logging.getLogger(__name__)

PROGRESS_FILE = "_step2_progress.json"
DATA_FILE = "step2_cmpn_area.parquet"
TASK_FILE = "step2_tasks.parquet"

SIDO_SEOUL = "110000"


def load_tasks() -> pd.DataFrame:
    p = SETTINGS.data_processed / TASK_FILE
    if not p.exists():
        raise FileNotFoundError(
            f"{p} 가 없다. 먼저 `python -m src.select_candidates` 실행."
        )
    return pd.read_parquet(p)


def load_progress() -> set[tuple[str, str, str]]:
    p = SETTINGS.data_processed / PROGRESS_FILE
    if not p.exists():
        return set()
    return {tuple(t) for t in json.loads(p.read_text(encoding="utf-8"))}


def save_progress(done: set[tuple[str, str, str]]) -> None:
    SETTINGS.data_processed.mkdir(parents=True, exist_ok=True)
    (SETTINGS.data_processed / PROGRESS_FILE).write_text(
        json.dumps(sorted(done), ensure_ascii=False), encoding="utf-8"
    )


def crawl(limit: int) -> None:
    client = HiraClient()
    tasks = load_tasks()
    done = load_progress()
    logger.info("total tasks=%d, done=%d", len(tasks), len(done))

    rows: list[dict] = []
    n_calls = 0
    started = time.time()
    try:
        for _, t in tasks.iterrows():
            key = (str(t["diag_ym"]), str(t["cmpn_cd"]), str(t["sggu"]))
            if key in done:
                continue
            if n_calls >= limit:
                logger.info("daily limit reached")
                break
            params = dict(
                diagYm=str(t["diag_ym"]),
                cmpnCd=str(t["cmpn_cd"]),
                insupTp="4",
                cpmdPrscTp="01",
                sidoCd=SIDO_SEOUL,
                sgguCd=str(t["sggu"]),
            )
            try:
                items = client.collect_all("cmpn_area", params)
            except Exception as e:
                logger.warning("skip %s: %s", key, e)
                continue
            for it in items:
                rows.append(dict(
                    period=it.get("diagYm", key[0]),
                    cmpn_cd=it.get("cmpnCd", key[1]),
                    cmpn_name=it.get("cmpnCdNm"),
                    atc_code=it.get("atcCd"),
                    region_code=it.get("sgguCd", key[2]),
                    region_name=it.get("sgguCdNm"),
                    insup_tp=it.get("insupTpCd"),
                    claim_count=int(float(it.get("totUseQty") or 0)),
                    claim_amount=int(float(it.get("msupUseAmt") or 0)),
                ))
            done.add(key)
            n_calls += 1
            save_progress(done)
            if n_calls % 10 == 0:
                _persist(rows)
                rows = []
                logger.info("progress: %d/%d (+%d this run, %.0fs)", len(done), len(tasks), n_calls, time.time()-started)
    finally:
        save_progress(done)
        if rows:
            _persist(rows)
        logger.info("done=%d/%d, fetched=%d", len(done), len(tasks), n_calls)


def _persist(rows: list[dict]) -> None:
    if not rows:
        return
    df = pd.DataFrame(rows)
    out = SETTINGS.data_processed / DATA_FILE
    if out.exists():
        existing = pd.read_parquet(out)
        df = pd.concat([existing, df], ignore_index=True).drop_duplicates(
            subset=["period", "cmpn_cd", "region_code", "insup_tp"]
        )
    df.to_parquet(out, index=False)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=9000)
    args = p.parse_args()
    crawl(args.limit)


if __name__ == "__main__":
    main()
