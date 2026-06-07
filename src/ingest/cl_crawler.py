"""3단계 의료기관 종별 크롤러 — G 패턴(의원의 오리지널 회피 의심) 입증용.

`getCmpnClList1.2` 호출. 입력: 2단계에서 추출한 후보 성분 + 4개 기관종.

기관종 코드 (작은 세트로 한정 — 핵심만):
  01: 상급종합병원
  11: 종합병원
  31: 의원
  81: 약국 (조제기준일 때만 의미)

전체 약 60,000콜 (10 성분 × 4 종별 × 25 시군구 × 120 월 / 두세 약효).
실제로는 후보 성분을 5~10개로 좁혀 30~60k 운용.

작업표는 `data/processed/step3_tasks.parquet` 에 미리 저장 후 이 크롤러가 소비.
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

PROGRESS_FILE = "_step3_progress.json"
DATA_FILE = "step3_cmpn_cl.parquet"
TASK_FILE = "step3_tasks.parquet"

SIDO_SEOUL = "110000"

# 비교 핵심 기관종 — 의원 vs 종합·상급종합 비교가 G 패턴의 본질
KEY_CL_CODES = ["01", "11", "31", "81"]
CL_NAMES = {
    "01": "상급종합병원",
    "11": "종합병원",
    "21": "병원",
    "31": "의원",
    "41": "치과병원",
    "51": "치과의원",
    "61": "조산원",
    "71": "보건의료원",
    "81": "약국",
    "91": "한방병원",
    "92": "한의원",
}


def load_tasks() -> pd.DataFrame:
    p = SETTINGS.data_processed / TASK_FILE
    if not p.exists():
        raise FileNotFoundError(
            f"{p} 가 없다. 먼저 `python -m src.select_candidates --step 3` 실행."
        )
    return pd.read_parquet(p)


def load_progress() -> set[tuple[str, str, str, str]]:
    p = SETTINGS.data_processed / PROGRESS_FILE
    if not p.exists():
        return set()
    return {tuple(t) for t in json.loads(p.read_text(encoding="utf-8"))}


def save_progress(done: set[tuple[str, str, str, str]]) -> None:
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
            key = (str(t["diag_ym"]), str(t["cmpn_cd"]), str(t["sggu"]), str(t["cl_cd"]))
            if key in done:
                continue
            if n_calls >= limit:
                logger.info("daily limit reached")
                break
            params = dict(
                diagYm=key[0],
                cmpnCd=key[1],
                insupTp="4",
                cpmdPrscTp="01",
                sidoCd=SIDO_SEOUL,
                sgguCd=key[2],
                clCd=key[3],
            )
            try:
                items = client.collect_all("cmpn_cl", params)
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
                    cl_cd=it.get("clCd", key[3]),
                    cl_name=it.get("clCdNm", CL_NAMES.get(key[3], key[3])),
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
                logger.info("progress: %d/%d (+%d this run, %.0fs)",
                            len(done), len(tasks), n_calls, time.time()-started)
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
            subset=["period", "cmpn_cd", "region_code", "cl_cd", "insup_tp"]
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
