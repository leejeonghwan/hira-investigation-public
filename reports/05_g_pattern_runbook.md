# G 패턴 (의원 오리지널 회피) 입증 워크북

본 패턴은 데이터로 추적 가능한 **유착 정황의 가장 강한 시그널**이다.
회사 단정 보도는 여전히 어렵지만, "구조적 의심 정황" 보도와 "특정 회사·성분의 비정상 처방 패턴" 보도가 가능하다.

## 가설

같은 성분(같은 효과)에 가격이 절반 이하인 제네릭이 충분히 있는데도, 의원(31)의 오리지널 처방 점유율이 종합병원(11)·상급종합(01)보다 유의미하게 높다면, 의학적으로 설명되지 않는다.

가능한 설명:
- 제약사 영업·리베이트 (의원은 영업 접점이 가장 가까움)
- 학회·교육 의존 (제약사 후원 학회의 영향)
- 종합병원 처방 답습 (대형병원에서 받던 약을 동네 의원에서 유지)

## 입증 데이터 흐름

```
1단계 (완료 가정) → 후보 약효 5개 선정
        ↓
2단계 (완료 가정) → 후보 약효의 성분별 시계열 → 약가마스터 join 으로 오리지널 식별
        ↓
3단계 ← NEW. 핵심 후보 성분 5~10개 × 4 기관종 × 25 시군구 × 120월
                                                = 60,000 콜 (약 7일)
        ↓
H5 분석 → 의원 vs 병원 오리지널 점유율 격차 표
        ↓
검증 (전문가·공정위 DB·식약처 행정처분 cross)
        ↓
보도 가능: "○○ 성분, 의원의 오리지널 처방 비중이 종합병원보다 ○○%p 높다.
          제네릭 ○종이 절반 가격임에도. 영업·인센티브 구조 의심"
```

## 3단계 실행

### 작업표 생성

`src/select_candidates.py` 에 step3 모드 추가 필요. 임시로는 직접 작업표 생성:

```bash
python -c "
import pandas as pd
from src.config import SETTINGS

# 예시: 2단계에서 G 후보로 추린 5개 성분
top_cmpns = ['cmpn_cd_1', 'cmpn_cd_2', 'cmpn_cd_3', 'cmpn_cd_4', 'cmpn_cd_5']
sggus = [f'110{str(i).zfill(3)}' for i in range(1, 26)]   # 서울 25개구
cl_cds = ['01', '11', '31', '81']  # 상급종합, 종합, 의원, 약국
yms = [f'{y:04d}{m:02d}' for y in range(2015, 2025) for m in range(1, 13)]

rows = [(ym, c, sg, cl) for ym in yms for c in top_cmpns for sg in sggus for cl in cl_cds]
df = pd.DataFrame(rows, columns=['diag_ym', 'cmpn_cd', 'sggu', 'cl_cd'])
df.to_parquet(SETTINGS.data_processed / 'step3_tasks.parquet', index=False)
print(f'tasks: {len(df)}')
"
```

### 크롤 실행

```bash
python -m src.ingest.cl_crawler --limit 27000   # 키 4개라면
```

## H5 분석 실행

```bash
python -c "
import pandas as pd
from src.config import SETTINGS
from src.ingest.reference_loader import load_price_master, load_give_list
from src.analysis import h5_clinic_brand_gap as h5

cl = pd.read_parquet(SETTINGS.data_processed / 'step3_cmpn_cl.parquet')
master = load_price_master()
give = load_give_list()

out = h5.detect(cl, master, give)
out.to_csv(SETTINGS.reports_tables / 'h5_clinic_brand_gap.csv', index=False)
print(f'후보 {len(out)}건. 의원-병원 격차 상위 10:')
print(out.head(10).to_string())
"
```

## 보도 강도별 산출

### 매우 강함 — 구조 비판
- "PPI 시장에서 의원의 오리지널 처방 비중이 종합병원보다 평균 26%p 높다. 의학적으로 설명 안 됨."
- 제조사 실명 인용 가능 (오리지널이라 약가마스터로 단정 가능)
- "병원 수준으로 의원이 처방했다면 연간 ○○○억 절감" 추정 수치 제시
- 정책 비판 (영업 규제·인센티브 구조 개혁) 자연스럽게 연결

### 강함 — 정황 의심
- 후보 의원·시군구 단위까지 좁힌 표 (단, 의원 실명 거론은 추가 근거 필요)
- 과거 공정위 적발 사례·식약처 행정처분 이력 매핑
- 회사·의원 측 입장 청취 후 ""의혹"" 단어 사용

### 약함 — 단정 보도 X
- 특정 의사 한 명의 부당 처방 (개인 단위 데이터 없음)
- 회사의 의도적 영업 활동 직접 입증 (영업 자료 필요)

## 검증 체크리스트 (보도 직전)

| 항목 | 도구·소스 |
| --- | --- |
| 적응증 차이로 설명되는가 (의원 환자 = 경증·외래, 병원 = 중증·입원) | 임상 자문 1~2명 |
| 동일 진단명 안에서도 격차 유지되는가 | `getCmpnSickList1.2` 추가 크롤 (옵션) |
| 공정위 과거 적발 사례 (같은 회사·같은 약효군) | kftc.go.kr 의결서 검색 |
| 식약처 영업정지·과징금 이력 | mfds.go.kr 공시 |
| 국감 자료 (보건복지위 회의록) | 의원실 문의 |
| 매출 정합성 (회사 IR, IQVIA) | 공시·구매 |
| 의·약사 인터뷰 (현장 풍토) | 1~2명 |
| 환자 인터뷰 (오리지널 처방 경험·고지 여부) | 환자단체 협조 |

## 데이터 한계 (보도에 명시할 것)

1. 의사 개인 단위 데이터 없음 — 시군구·기관종 합계만
2. 처방-조제 분리 환경의 약국·도매상 관계 못 봄
3. 환자 진단명 차원 없음 (의원=경증 vs 병원=중증 차이 배제 못함)
4. 영업사원 활동 직접 추적 불가 (당연히)
5. 가격 환산은 약가마스터 상한가 기준 — 실거래가는 다를 수 있음
6. 약가마스터에 누락된 비급여 의약품 분석 불가
