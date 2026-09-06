"""대시보드 data.js 생성기.

읽는 것:
  data/processed/suspect_drugs.json    (cmpnCd 목록)
  data/processed/_suspect_progress.json (진척)
  data/processed/suspect_sick.parquet  (시계열)
  data/processed/choline_sick.parquet  (콜린알포 별도 트랙, 있으면 합산)

쓰는 것:
  dashboard_suspect/data.js

실행:
  python -m dashboard_suspect.build_data
또는:
  python dashboard_suspect/build_data.py
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import SETTINGS  # noqa: E402

logger = logging.getLogger(__name__)

KOR_NAMES = {
    "choline_alfoscerate": "콜린알포세레이트",
    "oxiracetam": "옥시라세탐",
    "acetyl_l_carnitine": "아세틸엘카르니틴",
    "ginkgo_biloba": "은행엽 추출물",
    "citicoline": "시티콜린",
    "cerebrolysin": "세레브로라이신",
    "glucosamine": "글루코사민",
    "alprostadil": "알프로스타딜",
    "alpha_lipoic_acid": "알티옥트산(치옥타산)",
}

# 정책 이벤트 타임라인
TIMELINE = [
    {"date": "2020-08", "text": "콜린알포세레이트 본인부담률 30→80% 인상 (선별급여 전환)", "type": "active"},
    {"date": "2023-01", "text": "옥시라세탐 임상재평가 효과 입증 실패 (식약처)", "type": "active"},
    {"date": "2023-?", "text": "아세틸엘카르니틴 퇴출 (선별 종합)", "type": "terminal"},
    {"date": "2024-02", "text": "옥시라세탐 회수·폐기 명령 — 시장 퇴출", "type": "terminal"},
    {"date": "2024-03", "text": "콜린알포 환수 처분 취소 청구 대법원 패소 확정", "type": "active"},
    {"date": "2026-?", "text": "콜린알포 임상시험 제출기한 도래 (회사 회계 환수부채 인식)", "type": "active"},
]


def load_drugs() -> dict:
    p = SETTINGS.data_processed / "suspect_drugs.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def load_progress() -> set:
    p = SETTINGS.data_processed / "_suspect_progress.json"
    if not p.exists():
        return set()
    raw = json.loads(p.read_text(encoding="utf-8"))
    return {tuple(t) for t in raw}


def load_sick() -> pd.DataFrame:
    frames = []
    p1 = SETTINGS.data_processed / "suspect_sick.parquet"
    if p1.exists():
        frames.append(pd.read_parquet(p1))
    # 콜린알포 별도 트랙이 있으면 라벨 보강해 합산
    p2 = SETTINGS.data_processed / "choline_sick.parquet"
    if p2.exists():
        cho = pd.read_parquet(p2)
        if "gnl_nm_label" in cho.columns:
            cho["gnl_nm_label"] = cho["gnl_nm_label"].fillna("choline_alfoscerate")
        else:
            cho["gnl_nm_label"] = "choline_alfoscerate"
        frames.append(cho)
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    # 표준화
    if "gnl_nm_label" in df.columns:
        df["drug_key"] = df["gnl_nm_label"].fillna("unknown")
        # 콜린알포는 cmpn 라벨이 한국어일 수도 — 키워드로 매핑
        df.loc[
            df["drug_key"].str.contains("콜린|choline", case=False, na=False),
            "drug_key",
        ] = "choline_alfoscerate"
    return df


def build_drug_status(drugs_meta: dict, progress: set, sick_df: pd.DataFrame) -> list[dict]:
    expected_months = 120  # 2015.01~2024.12
    out = []
    for key, items in drugs_meta.items():
        n_cmpns = len(items)
        # 완료 = progress 안에 (ym, cmpnCd) 가 들어간 갯수 (suspect 진척만 — 콜린은 별도 트랙)
        cmpn_set = {it["cmpn_cd"] for it in items}
        completed = sum(1 for (ym, c) in progress if c in cmpn_set)
        expected = n_cmpns * expected_months
        if key == "choline_alfoscerate":
            # 콜린알포는 _choline_progress.json 따로
            chp = SETTINGS.data_processed / "_choline_progress.json"
            if chp.exists():
                raw = json.loads(chp.read_text(encoding="utf-8"))
                a_set = {tuple(t) for t in raw.get("A", [])}
                completed = len(a_set)
                expected = 6 * expected_months  # 콜린알포 6 cmpn
        status = (
            "missing" if n_cmpns == 0 else
            "complete" if completed >= expected else
            ("partial" if completed > 0 else "pending")
        )
        out.append({
            "key": key,
            "korName": KOR_NAMES.get(key, key),
            "nCmpns": n_cmpns,
            "completed": completed,
            "expected": expected,
            "progress": (completed / expected) if expected else 0,
            "status": status,
        })
    return out


def build_kpis_series(drug_status: list[dict], df: pd.DataFrame) -> dict:
    total_rows = len(df)
    if df.empty:
        return {
            "overallProgress": sum(d["progress"] for d in drug_status) / max(1, len(drug_status)),
            "totalRows": 0,
            "amount2024": 0,
            "totalSicks": 0,
            "amountByDrug": {},
            "sicksByDrug": {},
        }
    df["year"] = df["period"].astype(str).str[:4]
    by_drug_year = df.groupby(["drug_key", "year"])["claim_amount"].sum().reset_index()
    sicks_by_drug = df.groupby("drug_key")["sick_cd"].nunique().to_dict()
    amount_by_drug = df[df["year"] == "2024"].groupby("drug_key")["claim_amount"].sum().to_dict()
    if not amount_by_drug:
        # 2024 데이터 없으면 가장 최신 연도
        last_year = sorted(df["year"].unique())[-1]
        amount_by_drug = df[df["year"] == last_year].groupby("drug_key")["claim_amount"].sum().to_dict()

    years = sorted(df["year"].unique())
    series = {}
    for d in drug_status:
        vals = []
        for yr in years:
            row = by_drug_year[(by_drug_year["drug_key"] == d["key"]) & (by_drug_year["year"] == yr)]
            vals.append(float(row["claim_amount"].iloc[0]) if not row.empty else 0)
        series[d["key"]] = vals

    return {
        "kpis": {
            "overallProgress": sum(d["progress"] for d in drug_status) / max(1, len(drug_status)),
            "totalRows": total_rows,
            "amount2024": sum(amount_by_drug.values()),
            "totalSicks": int(df["sick_cd"].nunique()),
            "amountByDrug": {k: int(v) for k, v in amount_by_drug.items()},
            "sicksByDrug": {k: int(v) for k, v in sicks_by_drug.items()},
        },
        "series": {
            "years": years,
            "byDrug": series,
            "maxByYear": [max((series[d][i] for d in series), default=0) for i in range(len(years))],
            "markers": [{"year": "2020"}, {"year": "2023"}, {"year": "2024"}],
        },
    }


def build_sick_by_drug(df: pd.DataFrame, top: int = 12) -> dict:
    if df.empty:
        return {}
    y = df[df["period"].astype(str).str.startswith("2024")]
    if y.empty:
        # 최신
        last = sorted(df["period"].unique())[-1][:4]
        y = df[df["period"].astype(str).str.startswith(last)]
    out = {}
    for drug, sub in y.groupby("drug_key"):
        top_sicks = (
            sub.groupby(["sick_cd", "sick_name"])["claim_amount"].sum()
            .sort_values(ascending=False).head(top).reset_index()
        )
        out[drug] = [
            {"code": r.sick_cd, "name": r.sick_name, "amount": int(r.claim_amount)}
            for r in top_sicks.itertuples(index=False)
        ]
    return out


def run_status_label(progress: set, drug_status: list[dict]) -> str:
    if not progress and all(d["completed"] == 0 for d in drug_status):
        return "대기"
    avg = sum(d["progress"] for d in drug_status) / max(1, len(drug_status))
    if avg >= 0.99:
        return "완료"
    if avg > 0:
        return f"진행 중 ({avg*100:.0f}%)"
    return "대기"


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    drugs_meta = load_drugs()
    progress = load_progress()
    df = load_sick()
    if df.empty:
        logger.warning("suspect/choline parquet 비어있음 — 진척 상태만 표시")

    drug_status = build_drug_status(drugs_meta, progress, df)
    bundle = build_kpis_series(drug_status, df)
    sick_by_drug = build_sick_by_drug(df)

    payload = {
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "runStatus": run_status_label(progress, drug_status),
        "drugs": drug_status,
        "series": bundle["series"],
        "kpis": bundle["kpis"],
        "sickByDrug": sick_by_drug,
        "timeline": TIMELINE,
        "notes": [
            "심평원 공개 웹통계 '성분의 상병별'에서 수집한 콜린알포세레이트 cmpn × 월 × 상병 자료.",
            "건강보험·조제기준만 (보험자구분=4, 조제기준=201). 의료급여·보훈·처방기준 별도.",
            "현재 화면은 2024년 우선 복구분이다. 2018~2025 전체 시계열은 같은 스크립트로 추가 수집 가능.",
            "상병코드 prefix 'A' 는 HIRA 내부 표기 — 보도 시엔 ICD-10 표준 코드로 변환(예: AI10→I10).",
        ],
    }
    out_path = Path(__file__).parent / "data.js"
    out_path.write_text(
        "window.SUSPECT_DATA = " + json.dumps(payload, ensure_ascii=False, indent=2) + ";",
        encoding="utf-8",
    )
    print(f"saved: {out_path}")
    print(f"   상태: {payload['runStatus']}, 행수 {payload['kpis']['totalRows']:,}, 약물 {len(drug_status)}종")


if __name__ == "__main__":
    main()
