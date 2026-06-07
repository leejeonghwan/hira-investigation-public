"""콜린알포세레이트 전용 입체 크롤러.

세 트랙을 한 스크립트에서 운용:
  A  cmpn_sick  : 성분 × 상병 × 월       — 전국 합산. sickCd 빼면 1콜에 200상병
                  (6 성분 × 120월 × ~6페이지 ≈ 4,300 콜)
  B  cmpn_area  : 성분 × 시군구 × 월     — 6×25×120 = 18,000 콜
  C  cmpn_cl    : 성분 × 시군구 × 종별 × 월  — 6×25×4×120 = 72,000 콜

진행 상태:
  data/processed/_choline_progress.json (트랙별 키 셋 보관)

산출:
  data/processed/choline_sick.parquet  (전국, 월, 성분, 상병)
  data/processed/choline_area.parquet  (월, 성분, 시군구)
  data/processed/choline_cl.parquet    (월, 성분, 시군구, 기관종)

사용:
  python -m src.ingest.choline_crawler --tracks A --limit 5000
  python -m src.ingest.choline_crawler --tracks A,B,C --limit 9000
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

# 콜린알포세레이트 6개 일반명코드 (대시보드 data.js 와 약가마스터로 확인)
CHOLINE_CMPN = {
    "138101ACH": "콜린알포세레이트 캡슐",
    "138101ACS": "콜린알포세레이트 연질캡슐(시장 메인)",
    "138101ATB": "콜린알포세레이트 정제",
    "138103ASY": "콜린알포세레이트 시럽 138103",
    "138104ASY": "콜린알포세레이트 시럽 138104",
    "138130BIJ": "콜린알포세레이트 주사",
}

SIDO_SEOUL = "110000"
SGGUS_SEOUL = [f"110{str(i).zfill(3)}" for i in range(1, 26)]
KEY_CL = ["01", "11", "31", "81"]  # 상급종합·종합·의원·약국

PROGRESS_FILE = "_choline_progress.json"
START_YM = 201501
END_YM = 202412


def year_months(start: int, end: int):
    y, m = divmod(start, 100)
    while y * 100 + m <= end:
        yield f"{y:04d}{m:02d}"
        m += 1
        if m > 12:
            y += 1
            m = 1


def load_progress() -> dict[str, set[tuple]]:
    p = SETTINGS.data_processed / PROGRESS_FILE
    if not p.exists():
        return {"A": set(), "B": set(), "C": set()}
    raw = json.loads(p.read_text(encoding="utf-8"))
    return {k: {tuple(t) for t in v} for k, v in raw.items()}


def save_progress(done: dict[str, set[tuple]]) -> None:
    SETTINGS.data_processed.mkdir(parents=True, exist_ok=True)
    serial = {k: sorted(list(t) for t in v) for k, v in done.items()}
    (SETTINGS.data_processed / PROGRESS_FILE).write_text(
        json.dumps(serial, ensure_ascii=False), encoding="utf-8"
    )


def _persist(rows: list[dict], filename: str) -> None:
    if not rows:
        return
    df = pd.DataFrame(rows)
    out = SETTINGS.data_processed / filename
    if out.exists():
        existing = pd.read_parquet(out)
        df = pd.concat([existing, df], ignore_index=True)
        # 트랙별 dedup 키
        if "cl_cd" in df.columns:
            df = df.drop_duplicates(subset=["period", "gnl_nm_cd", "region_code", "cl_cd"])
        elif "region_code" in df.columns:
            df = df.drop_duplicates(subset=["period", "gnl_nm_cd", "region_code"])
        else:
            df = df.drop_duplicates(subset=["period", "gnl_nm_cd", "sick_cd"])
    df.to_parquet(out, index=False)


def crawl_track_a(client: HiraClient, done: set, budget: int) -> int:
    """A 트랙: 성분 × 상병 × 월. 전국 합산. page 자동 반복."""
    rows: list[dict] = []
    n = 0
    for ym in year_months(START_YM, END_YM):
        for cmpn, label in CHOLINE_CMPN.items():
            key = (ym, cmpn)
            if key in done:
                continue
            if n >= budget:
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
                logger.warning("[A] skip %s %s: %s", ym, cmpn, e)
                continue
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
            done.add(key)
            n += 1
            if n % 10 == 0:
                _persist(rows, "choline_sick.parquet")
                rows = []
                logger.info("[A] +%d done in run, total done=%d", n, len(done))
        if n >= budget:
            break
    _persist(rows, "choline_sick.parquet")
    return n


def crawl_track_b(client: HiraClient, done: set, budget: int) -> int:
    """B 트랙: 성분 × 시군구 × 월."""
    rows: list[dict] = []
    n = 0
    for ym in year_months(START_YM, END_YM):
        for cmpn, label in CHOLINE_CMPN.items():
            for sggu in SGGUS_SEOUL:
                key = (ym, cmpn, sggu)
                if key in done:
                    continue
                if n >= budget:
                    break
                params = dict(
                    diagYm=ym,
                    gnlNmCd=cmpn,
                    insupTp="4",
                    cpmdPrscTp="01",
                    sidoCd=SIDO_SEOUL,
                    sgguCd=sggu,
                )
                try:
                    items = client.collect_all("cmpn_area", params)
                except Exception as e:
                    logger.warning("[B] skip %s: %s", key, e)
                    continue
                for it in items:
                    rows.append(dict(
                        period=it.get("diagYm", ym),
                        gnl_nm_cd=it.get("gnlNmCd", cmpn),
                        gnl_nm_label=label,
                        region_code=it.get("sgguCd", sggu),
                        region_name=it.get("sgguCdNm"),
                        insup_tp=it.get("insupTpCd"),
                        claim_count=int(float(it.get("totUseQty") or 0)),
                        claim_amount=int(float(it.get("msupUseAmt") or 0)),
                    ))
                done.add(key)
                n += 1
                if n % 25 == 0:
                    _persist(rows, "choline_area.parquet")
                    rows = []
                    logger.info("[B] +%d in run, total done=%d", n, len(done))
            if n >= budget:
                break
        if n >= budget:
            break
    _persist(rows, "choline_area.parquet")
    return n


def crawl_track_c(client: HiraClient, done: set, budget: int) -> int:
    """C 트랙: 성분 × 시군구 × 기관종 × 월."""
    rows: list[dict] = []
    n = 0
    for ym in year_months(START_YM, END_YM):
        for cmpn, label in CHOLINE_CMPN.items():
            for sggu in SGGUS_SEOUL:
                for cl in KEY_CL:
                    key = (ym, cmpn, sggu, cl)
                    if key in done:
                        continue
                    if n >= budget:
                        break
                    params = dict(
                        diagYm=ym,
                        gnlNmCd=cmpn,
                        insupTp="4",
                        cpmdPrscTp="01",
                        sidoCd=SIDO_SEOUL,
                        sgguCd=sggu,
                        clCd=cl,
                    )
                    try:
                        items = client.collect_all("cmpn_cl", params)
                    except Exception as e:
                        logger.warning("[C] skip %s: %s", key, e)
                        continue
                    for it in items:
                        rows.append(dict(
                            period=it.get("diagYm", ym),
                            gnl_nm_cd=it.get("gnlNmCd", cmpn),
                            gnl_nm_label=label,
                            region_code=it.get("sgguCd", sggu),
                            region_name=it.get("sgguCdNm"),
                            cl_cd=it.get("clCd", cl),
                            cl_name=it.get("clCdNm"),
                            insup_tp=it.get("insupTpCd"),
                            claim_count=int(float(it.get("totUseQty") or 0)),
                            claim_amount=int(float(it.get("msupUseAmt") or 0)),
                        ))
                    done.add(key)
                    n += 1
                    if n % 25 == 0:
                        _persist(rows, "choline_cl.parquet")
                        rows = []
                        logger.info("[C] +%d in run, total done=%d", n, len(done))
                if n >= budget:
                    break
            if n >= budget:
                break
        if n >= budget:
            break
    _persist(rows, "choline_cl.parquet")
    return n


def crawl(tracks: list[str], limit: int) -> None:
    client = HiraClient()
    done = load_progress()
    started = time.time()
    remaining = limit
    try:
        for t in tracks:
            if remaining <= 0:
                break
            if t == "A":
                n = crawl_track_a(client, done["A"], remaining)
            elif t == "B":
                n = crawl_track_b(client, done["B"], remaining)
            elif t == "C":
                n = crawl_track_c(client, done["C"], remaining)
            else:
                logger.warning("unknown track: %s", t)
                continue
            remaining -= n
            save_progress(done)
            logger.info("Track %s done +%d calls (remaining budget %d)", t, n, remaining)
    finally:
        save_progress(done)
        logger.info(
            "TOTAL elapsed %.0fs. A=%d, B=%d, C=%d",
            time.time() - started, len(done["A"]), len(done["B"]), len(done["C"]),
        )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--tracks", default="A,B,C", help="콤마 구분, 우선순위 A→B→C")
    p.add_argument("--limit", type=int, default=9000)
    args = p.parse_args()
    crawl([t.strip().upper() for t in args.tracks.split(",")], args.limit)


if __name__ == "__main__":
    main()
