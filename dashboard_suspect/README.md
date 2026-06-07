# 의심 의약품 8종 시리즈 대시보드

콜린알포세레이트 + 같은 결의 의심 의약품 8종(옥시라세탐·아세틸엘카르니틴·은행엽·시티콜린·세레브로라이신·글루코사민·알프로스타딜·알티옥트산) 의 수집 진행과 결과를 한 화면에서 본다.

## 구성

```
dashboard_suspect/
├── index.html       정적 페이지
├── styles.css
├── app.js           자체 캔버스 렌더링 (의존성 없음)
├── data.js          빌드 결과 (초기엔 mock)
├── build_data.py    parquet → data.js
└── README.md
```

## 갱신 흐름

```bash
# 1) 약가마스터에서 cmpnCd 추출 (1회)
python -m src.select_suspect_drugs

# 2) 크롤 실행 (주기적으로)
python -m src.ingest.suspect_crawler --limit 9000

# 3) 대시보드 갱신
python -m dashboard_suspect.build_data

# 4) 보기
open dashboard_suspect/index.html
```

크롤 진행 중에도 build_data 를 돌리면 부분 진척이 반영됩니다.

## 화면 구성

1. **KPI 4종** — 전체 진척, 수집 행수, 2024 청구합계, 사용된 상병 종류
2. **약물별 진척표** — 9 약물(콜린알포 포함) cmpnCd·완료·진척바·상태
3. **약물별 10년 시계열** — 멀티 라인, 정책 시점 마커
4. **2024 청구액 비교** — 가로 막대
5. **상병 다양성** — 약물별 누적 상병 수
6. **선택 약물의 2024 상위 상병** — 드롭다운 약물 선택 → 상위 12 상병
7. **정책 이벤트 타임라인** — 본인부담 인상·임상재평가 실패·퇴출 등
