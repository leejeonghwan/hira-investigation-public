# 2단계 운영 가이드 — 1단계 완료 후 무엇을 어떤 순서로

본 가이드는 1단계 크롤(36,000 콜) 이 끝난 다음 날 시작하는 절차다.
목표: 제조사·오리지널 명시 가능한 본격 보도 데이터 확보.

## 입력 의존성

| 데이터 | 출처 | 형식 | 비고 |
| --- | --- | --- | --- |
| 1단계 결과 | `data/processed/macro_seoul_meft.parquet` | parquet | 자동 |
| 약가마스터 | data.go.kr 15067462 다운로드 | CSV | `data/reference/drug_price_master.csv` 로 배치 |
| 약제급여목록표 | hira.or.kr > 제도·정책 > 약제기준정보 > 목록표 | XLSX | `data/reference/drug_give_list.xlsx` 로 배치. **약효분류 ↔ 성분 매핑이 여기에만 있다** |
| 인구 데이터(선택) | KOSIS 시군구 인구 | CSV | H4 인구 정규화용 |

## 절차

### 0. 사전 다운로드 (10분)

```bash
mkdir -p data/reference
# (a) 약가마스터 — 브라우저로 https://www.data.go.kr/data/15067462/fileData.do "다운로드" 클릭
mv ~/Downloads/건강보험심사평가원_약가마스터_의약품표준코드_*.csv \
   data/reference/drug_price_master.csv
# (b) 약제급여목록표 — https://www.hira.or.kr/rd/dur/durList.do 비슷한 위치, XLSX
mv ~/Downloads/약제급여목록표*.xlsx data/reference/drug_give_list.xlsx
```

### 1. 후보 약효·성분·시군구 자동 선정 (5분)

```bash
python -m src.select_candidates --top 5 --sggu-top 10
```

- 1단계 데이터에 surge.detect 적용 → 상위 5개 약효
- 청구액 큰 10개 시군구 추출
- 약제급여목록표로 그 약효들 안의 성분 목록 확보
- `data/processed/step2_tasks.parquet` 와 `step2_meta.json` 생성

기대 작업량 (성분 5~15개 / 약효 가정):
```
5 약효 × 10 성분 평균 × 10 시군구 × 120 월 = 60,000 콜
≈ 7일 (일일 9,000 콜 한도)
```

### 2. 2단계 크롤 (7일, 매일 1회)

```bash
python -m src.ingest.cmpn_crawler --limit 9000   # 매일
```

진척 확인:
```bash
python -c "import json,pathlib;p=json.loads(pathlib.Path('data/processed/_step2_progress.json').read_text());print(f'{len(p)}/?')"
```

### 3. H2 + H3 본격 분석 (즉시)

```bash
python -c "
import pandas as pd
from src.config import SETTINGS
from src.ingest.reference_loader import load_price_master, load_give_list
from src.analysis import h2_concentration_real as h2, h3_brand_vs_generic_real as h3

cmpn = pd.read_parquet(SETTINGS.data_processed / 'step2_cmpn_area.parquet')
master = load_price_master()
give = load_give_list()

h2_out = h2.detect(cmpn, master)
h2_out.to_csv(SETTINGS.reports_tables / 'h2_concentration_real.csv', index=False)

h3_out = h3.detect(cmpn, give)
h3_out.to_csv(SETTINGS.reports_tables / 'h3_brand_vs_generic_real.csv', index=False)
"
```

산출:
- `h2_concentration_real.csv` — 성분별 오리지널·제조사 식별 + 단가 + 청구금액. **회사 단정 보도 후보**
- `h3_brand_vs_generic_real.csv` — 성분별 오리지널 vs 제네릭 가격차 + 잠재 절감액 (50%/70% 대체 시나리오)

### 4. 검증 체크리스트 (각 보도 후보 의약품 단위)

- [ ] 적응증 확대·재허가 이력 (식약처 의약품통합정보시스템 KPIS)
- [ ] 약가 인하 고시 이력 (보건복지부)
- [ ] 다국적/국내 라이선스 인수 이력 (오리지널 제조사 변경 가능)
- [ ] 코로나19·외생 충격 영향 분리 (연도 더미)
- [ ] 다른 약효군 동시 변화 vs 단독 변화 (대조군 비교)
- [ ] 임상 적절성 (전문의 자문 1~2회)

### 5. 보도 가능 산출물

| 산출물 | 근거 데이터 | 보도 강도 |
| --- | --- | --- |
| 약효별 10년 청구 추이 | 1단계 + 2단계 | 매우 강함 |
| 성분별 오리지널 점유율 시계열 | 2단계 + 마스터 | 강함 |
| 잠재 절감액 추정 (시나리오) | 2단계 + 마스터 + 목록표 | **이 보도의 본기사** |
| 시군구 핫스팟 + 인구 정규화 지도 | 1·2단계 + KOSIS | 시각화 본기사 |
| 제조사 단정 (오리지널) | 마스터 직접 인용 | 가능 |
| 제조사 단정 (제네릭 점유) | 불가 (IQVIA 보강 필요) | 별도 |

## 주의

- 약가마스터는 누적 매핑이라 급여삭제 품목도 포함. 분석 시점에 살아있는 품목인지 약제급여목록표 cross-check.
- 같은 성분에 다국적 + 국내 제네릭이 섞이면 평균 가격이 왜곡됨. 가격 분포(분위수)로도 같이 보기.
- 시군구 단위는 의원 입지·거주지·요양시설 등 인구 외 요인이 큼. 단정 보도 자제.
