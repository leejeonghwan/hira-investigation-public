"""의심 의약품 8종의 일반명코드(gnlNmCd / cmpn_cd) 자동 추출.

약가마스터(data.go.kr 15067462) 의 'kor_name' 컬럼을 키워드로 검색해
각 의심약의 cmpnCd 목록을 추리고, suspect_drugs.json 으로 저장.

이 JSON 을 suspect_crawler 가 읽어 8종을 한 번에 크롤한다.

사용:
  python -m src.select_suspect_drugs
  cat data/processed/suspect_drugs.json | python -m json.tool
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

from .config import SETTINGS
from .ingest.reference_loader import load_price_master

logger = logging.getLogger(__name__)

# 8종 의심 의약품 키워드 — kor_name 에서 검색
# (대소문자·공백 무시 contains 매칭)
SUSPECT_KEYWORDS: dict[str, list[str]] = {
    # 뇌영양제 카테고리 — 콜린알포와 같은 결
    "oxiracetam": ["옥시라세탐", "옥시라세탐", "oxiracetam"],
    "acetyl_l_carnitine": ["아세틸엘카르니틴", "아세틸엘-카르니틴", "acetyl-l-carnitine", "acetyl l carnitine"],
    "ginkgo_biloba": ["은행엽", "은행잎", "ginkgo"],
    "citicoline": ["시티콜린", "citicoline"],
    "cerebrolysin": ["세레브로라이신", "cerebrolysin"],
    # 기타 의심 카테고리
    "glucosamine": ["글루코사민", "glucosamine"],
    "alprostadil": ["알프로스타딜", "alprostadil"],
    "alpha_lipoic_acid": ["알티옥트산", "치옥타산", "치옥트산", "alpha-lipoic", "alpha lipoic", "thioctic"],
}

CHOLINE_KEYWORDS = ["콜린알포세레이트", "콜린알포", "choline alfoscerate"]


def find_cmpn_cds(master: pd.DataFrame, keywords: list[str]) -> list[dict]:
    """kor_name 에서 키워드 검색 → 매칭된 cmpn_cd + 대표 sample."""
    cols = ["cmpn_cd", "kor_name", "maker", "atc_code"]
    sub = master[master["kor_name"].fillna("").apply(
        lambda s: any(k.lower() in s.lower() for k in keywords)
    )]
    if sub.empty:
        return []
    grouped = sub.groupby("cmpn_cd").agg(
        sample_name=("kor_name", "first"),
        sample_maker=("maker", "first"),
        atc=("atc_code", "first"),
        n_items=("kor_name", "count"),
    ).reset_index()
    return grouped.to_dict("records")


def build() -> dict:
    master = load_price_master()
    logger.info("master rows: %d", len(master))
    out: dict[str, list[dict]] = {}
    # 콜린알포는 검증용 — 이미 알고 있는 cmpnCd 와 매칭되는지 확인
    out["choline_alfoscerate"] = find_cmpn_cds(master, CHOLINE_KEYWORDS)
    for label, kws in SUSPECT_KEYWORDS.items():
        out[label] = find_cmpn_cds(master, kws)
    return out


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    found = build()
    out_path = SETTINGS.data_processed / "suspect_drugs.json"
    out_path.write_text(json.dumps(found, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"저장: {out_path}\n")
    for drug, items in found.items():
        if not items:
            print(f"  ⚠ {drug}: 0 hits (키워드 보정 또는 약가마스터 확인 필요)")
            continue
        cmpns = [r["cmpn_cd"] for r in items]
        sample = items[0]
        print(f"  ✓ {drug}: {len(cmpns)} cmpnCd → {cmpns[:6]}{'...' if len(cmpns) > 6 else ''}")
        print(f"      예시: {sample['sample_name']} ({sample['sample_maker']})")


if __name__ == "__main__":
    main()
