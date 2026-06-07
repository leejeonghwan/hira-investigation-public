"""1단계 거시 크롤러 — 재개 가능한 청크 실행기.

대상
----
서울 25개 시군구 × 우선 약효분류군 12개 × 10년치(2015.01~2024.12) × 건강보험·조제기준.
총 작업량: 25 × 12 × 120 = 36,000 콜.

운용
----
- 일일 한도(`DAILY_LIMIT`, 기본 9,000)에 도달하면 자동 정지하고 다음 날 이어 한다.
- 체크포인트: `data/processed/_macro_progress.json` 에 완료된 (ym, meft, sggu) 기록.
- 부분 결과는 매 청크마다 parquet append 가능하도록 ym 별로 떨어뜨림.

사용
----
    python -m src.ingest.macro_crawler           # 오늘 분량(9,000 콜)만
    python -m src.ingest.macro_crawler --limit 500   # 짧은 시험
    python -m src.ingest.macro_crawler --resume      # 명시 이어걸기
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Iterable

import pandas as pd

from ..config import SETTINGS
from .hira_client import HiraClient

logger = logging.getLogger(__name__)


# 우선 약효분류군 (3자리 코드, HIRA 약제급여목록표 분류)
PRIORITY_MEFT = {
    "117": "정신신경용제",
    "118": "기타의 중추신경계용약",
    "214": "혈관확장제(협심증·뇌순환)",
    "218": "동맥경화용제(스타틴)",
    "232": "소화성궤양용제(PPI)",
    "239": "기타의 소화기관용약",
    "264": "통풍치료제",
    "313": "비타민B제",
    "333": "혈액응고저지제(항응고)",
    "421": "항악성종양제",
    "611": "주로 그람양성균 작용 항생제",
    "612": "주로 그람음성균 작용 항생제",
}

# 서울 25개 시군구 (sgguCd)
SIDO_SEOUL = "110000"
SGGUS_SEOUL = [f"110{str(i).zfill(3)}" for i in range(1, 26)]

# 10년치 진료년월
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


def all_tasks() -> list[tuple[str, str, str]]:
    """(diagYm, meftDivNo, sgguCd) 작업 단위 전체."""
    return [
        (ym, meft, sggu)
        for ym in year_months(START_YM, END_YM)
        for meft in PRIORITY_MEFT
        for sggu in SGGUS_SEOUL
    ]


def load_progress() -> set[tuple[str, str, str]]:
    p = SETTINGS.data_processed / "_macro_progress.json"
    if not p.exists():
        return set()
    try:
        return {tuple(t) for t in json.loads(p.read_text(encoding="utf-8"))}
    except Exception:
        return set()


def save_progress(done: set[tuple[str, str, str]]) -> None:
    SETTINGS.data_processed.mkdir(parents=True, exist_ok=True)
    p = SETTINGS.data_processed / "_macro_progress.json"
    p.write_text(json.dumps(sorted(done), ensure_ascii=False), encoding="utf-8")


def crawl(limit: int) -> None:
    client = HiraClient()
    tasks = all_tasks()
    done = load_progress()
    todo = [t for t in tasks if t not in done]
    logger.info("total=%d, done=%d, todo=%d, today_limit=%d", len(tasks), len(done), len(todo), limit)

    rows: list[dict] = []
    n_calls = 0
    started = time.time()
    try:
        for (ym, meft, sggu) in todo:
            if n_calls >= limit:
                logger.info("daily limit reached -> stopping")
                break
            params = dict(
                diagYm=ym,
                meftDivNo=meft,
                insupTp="4",
                cpmdPrscTp="01",
                sidoCd=SIDO_SEOUL,
                sgguCd=sggu,
            )
            try:
                items = client.collect_all("meft_div_area", params)
            except Exception as e:
                logger.warning("skip %s %s %s: %s", ym, meft, sggu, e)
                continue
            for it in items:
                rows.append(dict(
                    period=it.get("diagYm", ym),
                    atc_class=it.get("meftDivNo", meft),
                    ingredient=it.get("meftDivNoNm", PRIORITY_MEFT.get(meft, meft)),
                    region_code=it.get("sgguCd", sggu),
                    region_name=it.get("sgguCdNm"),
                    sido_code=it.get("sidoCd", SIDO_SEOUL),
                    insup_tp=it.get("insupTpCd"),
                    claim_count=int(float(it.get("totUseQty") or 0)),
                    claim_amount=int(float(it.get("msupUseAmt") or 0)),
                ))
            done.add((ym, meft, sggu))
            n_calls += 1
            # 매 콜마다 progress 저장 (JSON 작아 쓰기 비용 미미). parquet 은 10콜에 한 번.
            save_progress(done)
            if n_calls % 10 == 0:
                _persist(rows)
                rows = []
                logger.info("progress: %d/%d (+%d this run, %.0fs)", len(done), len(tasks), n_calls, time.time()-started)
    finally:
        save_progress(done)
        if rows:
            _persist(rows)
        logger.info("done=%d/%d, fetched_this_run=%d", len(done), len(tasks), n_calls)


def _persist(rows: list[dict]) -> None:
    if not rows:
        return
    SETTINGS.data_processed.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    out = SETTINGS.data_processed / "macro_seoul_meft.parquet"
    if out.exists():
        existing = pd.read_parquet(out)
        df = pd.concat([existing, df], ignore_index=True).drop_duplicates(
            subset=["period", "atc_class", "region_code", "insup_tp"]
        )
    df.to_parquet(out, index=False)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=9000, help="today's call budget (default 9000)")
    args = p.parse_args()
    crawl(args.limit)


if __name__ == "__main__":
    main()
