"""약가마스터 + 약제급여목록표 로더.

약가마스터 (data.go.kr 15067462)
---------------------------------
- 파일: CSV, 약 30만 행 (한약재·기타 포함)
- 다운로드: https://www.data.go.kr/data/15067462/fileData.do "다운로드" 버튼
- 표준 컬럼 (실제 헤더):
    한글상품명, 업체명, 약품규격, 제품총수량, 제형구분, 포장형태,
    품목기준코드, 품목허가일자, 전문일반구분, 대표코드, 표준코드,
    제품코드(개정후), 일반명코드(성분명코드), 비고, 취소일자,
    양도양수적용(공고)일자, 양도양수종료일자, 일련번호생략여부,
    일련번호생략사유, 국제표준코드(ATC코드), 특수관리약품구분,
    의약품판독장비구분
- 약가마스터에는 **약효분류군이 없다**. 약효분류 ↔ 성분 매핑은 HIRA 약제급여목록표
  (https://www.hira.or.kr/rd/dur/durList.do?pgmid=HIRAA030035020000) 별도 다운.

약제급여목록표 (HIRA 홈페이지 다운로드)
---------------------------------
- 파일: XLSX
- 표준 컬럼:
    약효분류번호, 주성분코드, 제품명, 업체명, 규격, 단위, 상한금액, 투여,
    등재년월, 산정유형, 제형, ATC코드
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pandas as pd

from ..config import SETTINGS

logger = logging.getLogger(__name__)


# 약가마스터 한글 컬럼 → 영문 표준
PRICE_MASTER_RENAME = {
    "한글상품명": "kor_name",
    "업체명": "maker",
    "약품규격": "spec",
    "제형구분": "form",
    "품목기준코드": "item_seq",       # 품목 단위 식별자
    "품목허가일자": "auth_date",      # 오리지널/제네릭 판별용
    "전문일반구분": "rx_or_otc",
    "대표코드": "rep_code",
    "표준코드": "std_code",
    "제품코드(개정후)": "prod_code",
    "일반명코드(성분명코드)": "cmpn_cd",  # ← API 의 cmpnCd
    "취소일자": "cancel_date",
    "국제표준코드(ATC코드)": "atc_code",
}

GIVE_LIST_RENAME = {
    "약효분류번호": "meft_div_no",
    "주성분코드": "cmpn_cd",
    "제품명": "kor_name",
    "업체명": "maker",
    "규격": "spec",
    "단위": "unit",
    "상한금액": "price_upper",
    "투여": "route",
    "등재년월": "listed_ym",
    "산정유형": "calc_type",
    "제형": "form",
    "ATC코드": "atc_code",
}


def load_price_master(path: Optional[Path] = None) -> pd.DataFrame:
    """약가마스터 CSV 로드 + 표준화 + 한약재·취소 제거 옵션."""
    path = path or (SETTINGS.data_reference / "drug_price_master.csv")
    if not path.exists():
        raise FileNotFoundError(
            f"{path} 가 없다. data.go.kr 15067462 에서 다운로드해 reference/ 에 둬라."
        )
    logger.info("loading master %s", path)
    # 인코딩은 CP949 또는 UTF-8 BOM 둘 다 가능 — try 둘 다
    try:
        df = pd.read_csv(path, dtype=str, encoding="utf-8")
    except UnicodeDecodeError:
        df = pd.read_csv(path, dtype=str, encoding="cp949")
    df = df.rename(columns={k: v for k, v in PRICE_MASTER_RENAME.items() if k in df.columns})

    # 한약재·바코드 전용은 분석 제외
    if "form" in df.columns:
        df = df[~df["form"].fillna("").str.contains("한약재")]
    if "cmpn_cd" in df.columns:
        # cmpnCd 가 비어있는 것은 분석 불가
        df = df[df["cmpn_cd"].notna() & (df["cmpn_cd"].str.strip() != "")]

    if "auth_date" in df.columns:
        df["auth_date"] = pd.to_datetime(df["auth_date"], errors="coerce")
    if "cancel_date" in df.columns:
        df["cancel_date"] = pd.to_datetime(df["cancel_date"], errors="coerce")
    logger.info("master rows after filtering: %d, unique cmpn_cd: %d", len(df), df["cmpn_cd"].nunique())
    return df


def load_give_list(path: Optional[Path] = None) -> pd.DataFrame:
    """약제급여목록표 XLSX 로드 + 표준화."""
    path = path or (SETTINGS.data_reference / "drug_give_list.xlsx")
    if not path.exists():
        raise FileNotFoundError(
            f"{path} 가 없다. hira.or.kr > 제도·정책 > 약제기준정보 > 목록표 > 약제급여목록표 에서 받아라."
        )
    df = pd.read_excel(path, dtype=str)
    df = df.rename(columns={k: v for k, v in GIVE_LIST_RENAME.items() if k in df.columns})
    if "price_upper" in df.columns:
        df["price_upper"] = pd.to_numeric(df["price_upper"], errors="coerce")
    if "listed_ym" in df.columns:
        df["listed_ym"] = df["listed_ym"].astype(str).str.replace(r"\D", "", regex=True).str.slice(0, 6)
    return df


def build_cmpn_to_atc3(master: pd.DataFrame) -> pd.DataFrame:
    """성분코드 ↔ 약효분류군 3자리 매핑 (give_list 기반이 정석, 임시 fallback)."""
    if "atc_code" not in master.columns:
        return pd.DataFrame(columns=["cmpn_cd", "atc_code"])
    return master[["cmpn_cd", "atc_code"]].drop_duplicates()


def first_listed_per_cmpn(give: pd.DataFrame) -> pd.DataFrame:
    """성분별 최초 등재 품목 = 오리지널 후보. 두 번째 등재 = 제네릭 시작."""
    g = give.dropna(subset=["listed_ym", "cmpn_cd"]).sort_values("listed_ym")
    out = (
        g.groupby("cmpn_cd")
        .agg(
            original_listed=("listed_ym", "first"),
            original_maker=("maker", "first"),
            original_kor_name=("kor_name", "first"),
            original_price=("price_upper", "first"),
            n_items=("item_seq", "nunique") if "item_seq" in g.columns else ("kor_name", "size"),
        )
        .reset_index()
    )
    return out


def join_meft_to_cmpn(give: pd.DataFrame, meft_3digit: str) -> list[str]:
    """약효분류군 3자리 코드로 성분코드 리스트 추출."""
    sub = give[give["meft_div_no"].astype(str).str.startswith(meft_3digit)]
    return sorted(sub["cmpn_cd"].dropna().unique().tolist())
