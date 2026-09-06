"""심평원 공개 웹통계에서 콜린알포세레이트 상병별 자료를 수집한다.

OpenAPI cmpn_sick 이 500을 반복할 때 쓰는 우회 경로다.

입력:
  https://opendata.hira.or.kr/op/opc/olapGnlInfoTab3.do

출력:
  data/raw/hira_web_choline/{year}_{cmpn}.html
  data/processed/choline_sick.parquet
  data/processed/_choline_progress.json
  data/processed/suspect_drugs.json
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import time
from io import StringIO
from pathlib import Path

import pandas as pd
import requests
import urllib3

from ..config import SETTINGS

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

BASE = "https://opendata.hira.or.kr"
TAB3_URL = f"{BASE}/op/opc/olapGnlInfoTab3.do"
GNL_SEARCH_URL = f"{BASE}/op/opc/selectGnlList.do"

CHOLINE_CMPN = {
    "138101ACH": "choline alfoscerate",
    "138101ACS": "choline alfoscerate",
    "138101APD": "choline alfoscerate",
    "138101ATB": "choline alfoscerate",
    "138102BIJ": "choline alfoscerate",
    "138103ASY": "choline alfoscerate",
    "138104ASY": "choline alfoscerate",
    "138130BIJ": "choline alfoscerate",
}


def period_to_yyyymm(value: str) -> str:
    m = re.search(r"(\d{4})\D+(\d{1,2})", str(value))
    if not m:
        return str(value)
    return f"{m.group(1)}{int(m.group(2)):02d}"


def intish(value) -> int:
    if pd.isna(value):
        return 0
    return int(str(value).replace(",", "").replace(".0", "").strip() or 0)


def normalize_sick_code(value: str) -> str:
    # HIRA 웹통계는 ICD-10 앞에 A를 붙여 AI10처럼 표기한다.
    return str(value).strip()


def parse_table(html: str) -> pd.DataFrame:
    try:
        tables = pd.read_html(StringIO(html), flavor="lxml")
    except Exception as exc:
        logger.warning("표 파싱 실패(빈/깨진 페이지 건너뜀): %s", exc)
        return pd.DataFrame()
    target = None
    for table in tables:
        cols = {str(c).strip() for c in table.columns}
        if {"기간", "성분코드", "상병코드", "금액"}.issubset(cols):
            target = table
            break
    if target is None:
        return pd.DataFrame()

    df = target.rename(
        columns={
            "기간": "period",
            "성분코드": "gnl_nm_cd",
            "성분명": "gnl_nm_label",
            "상병코드": "sick_cd",
            "상병명": "sick_name",
            "순위": "rank",
            "수량": "claim_count",
            "금액": "claim_amount",
        }
    )
    df = df[df["sick_cd"].notna()].copy()
    df["period"] = df["period"].map(period_to_yyyymm)
    df["sick_cd"] = df["sick_cd"].map(normalize_sick_code)
    df["claim_count"] = df["claim_count"].map(intish)
    df["claim_amount"] = df["claim_amount"].map(intish)
    df["insup_tp"] = "4"
    return df[
        [
            "period",
            "gnl_nm_cd",
            "gnl_nm_label",
            "sick_cd",
            "sick_name",
            "insup_tp",
            "claim_count",
            "claim_amount",
        ]
    ]


def lookup_name(session: requests.Session, cmpn: str) -> str:
    try:
        resp = session.post(
            GNL_SEARCH_URL,
            data={"searchWrd1": cmpn},
            timeout=30,
            verify=False,
        )
        resp.raise_for_status()
        rows = resp.json()
        if rows:
            return rows[0].get("gnlNmCdNm") or CHOLINE_CMPN.get(cmpn, cmpn)
    except Exception as exc:
        logger.warning("성분명 조회 실패 %s: %s", cmpn, exc)
    return CHOLINE_CMPN.get(cmpn, cmpn)


def fetch_year(session: requests.Session, cmpn: str, name: str, year: int, gubun: str) -> str:
    payload = {
        "searchWrd": name,
        "olapCd": cmpn,
        "olapCdNm": name,
        "sDiagYm": f"{year}01",
        "eDiagYm": f"{year}12",
        "sYm": f"{year}-01",
        "eYm": f"{year}-12",
        "gubun": gubun,
        "tabGubun": "201",
        "st3Gubun": "100",
    }
    resp = session.post(TAB3_URL, data=payload, timeout=240, verify=False)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def write_progress(df: pd.DataFrame) -> None:
    done = sorted({(str(r.period), str(r.gnl_nm_cd)) for r in df.itertuples(index=False)})
    path = SETTINGS.data_processed / "_choline_progress.json"
    path.write_text(json.dumps({"A": done, "B": [], "C": []}, ensure_ascii=False), encoding="utf-8")


def write_drug_meta(codes: dict[str, str]) -> None:
    rows = [
        {
            "cmpn_cd": cmpn,
            "sample_name": name,
            "sample_maker": "",
            "atc": "",
            "n_items": 0,
        }
        for cmpn, name in codes.items()
    ]
    path = SETTINGS.data_processed / "suspect_drugs.json"
    path.write_text(
        json.dumps({"choline_alfoscerate": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def collect(years: list[int], codes: list[str], gubun: str) -> pd.DataFrame:
    SETTINGS.data_raw.mkdir(parents=True, exist_ok=True)
    SETTINGS.data_processed.mkdir(parents=True, exist_ok=True)
    raw_dir = SETTINGS.data_raw / "hira_web_choline"
    raw_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    # 심평원 서버는 기본 python-requests UA 를 막는다. 브라우저형 헤더 필수.
    session.headers.update({
        "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/126.0 Safari/537.36"),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        "Referer": BASE + "/op/opc/olapGnlInfoTab3.do",
    })
    # 워밍업 GET — 실패해도 재시도.
    for attempt in range(3):
        try:
            session.get(TAB3_URL, timeout=60, verify=False)
            break
        except Exception as exc:
            logger.warning("warmup GET 실패(%d/3): %s", attempt + 1, exc)
            time.sleep(3)

    frames = []
    names = {}
    for cmpn in codes:
        name = lookup_name(session, cmpn)
        names[cmpn] = name
        for year in years:
            raw_path = raw_dir / f"g{gubun}_{year}_{cmpn}.html"
            if raw_path.exists():
                html = raw_path.read_text(encoding="utf-8")
                logger.info("cached %s %s", year, cmpn)
            else:
                logger.info("fetch gubun=%s %s %s %s", gubun, year, cmpn, name)
                html = fetch_year(session, cmpn, name, year, gubun)
                raw_path.write_text(html, encoding="utf-8")
            df = parse_table(html)
            if df.empty:
                logger.warning("no table rows: %s %s", year, cmpn)
                continue
            frames.append(df)
            logger.info("rows %s %s: %d", year, cmpn, len(df))

    write_drug_meta(names)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True).drop_duplicates(
        subset=["period", "gnl_nm_cd", "sick_cd"]
    )
    out_path = SETTINGS.data_processed / "choline_sick.parquet"
    out.to_parquet(out_path, index=False)
    write_progress(out)
    logger.info("saved %s (%d rows)", out_path, len(out))
    return out


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", nargs="+", type=int, default=[2024])
    parser.add_argument("--codes", nargs="+", default=list(CHOLINE_CMPN))
    parser.add_argument(
        "--gubun",
        default="4",
        choices=["0", "4", "5", "7"],
        help="보험자구분: 0=전체, 4=건강보험, 5=의료급여, 7=보훈",
    )
    args = parser.parse_args()
    df = collect(args.years, args.codes, args.gubun)
    if df.empty:
        raise SystemExit("no rows collected")
    print(f"saved rows={len(df):,} years={sorted(df['period'].str[:4].unique())}")


if __name__ == "__main__":
    main()
