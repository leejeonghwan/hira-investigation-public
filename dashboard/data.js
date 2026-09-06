window.SUSPECT_DATA = {
  "generatedAt": "2026-07-15 12:29",
  "runStatus": "진행 중 (7%)",
  "drugs": [
    {
      "key": "choline_alfoscerate",
      "korName": "콜린알포세레이트",
      "nCmpns": 5,
      "completed": 53,
      "expected": 720,
      "progress": 0.07361111111111111,
      "status": "partial"
    }
  ],
  "series": {
    "years": [
      "2024"
    ],
    "byDrug": {
      "choline_alfoscerate": [
        361899720738.0
      ]
    },
    "maxByYear": [
      361899720738.0
    ],
    "markers": [
      {
        "year": "2020"
      },
      {
        "year": "2023"
      },
      {
        "year": "2024"
      }
    ]
  },
  "kpis": {
    "overallProgress": 0.07361111111111111,
    "totalRows": 5376,
    "amount2024": 361899720738,
    "totalSicks": 283,
    "amountByDrug": {
      "choline_alfoscerate": 361899720738
    },
    "sicksByDrug": {
      "choline_alfoscerate": 283
    }
  },
  "sickByDrug": {
    "choline_alfoscerate": [
      {
        "code": "AI10",
        "name": "본태성(원발성) 고혈압",
        "amount": 57159748738
      },
      {
        "code": "AF00",
        "name": "알츠하이머병에서의 치매(G30.-†)",
        "amount": 37428376749
      },
      {
        "code": "AI63",
        "name": "뇌경색증",
        "amount": 35928715816
      },
      {
        "code": "AF06",
        "name": "뇌손상, 뇌기능이상 및 신체질환에 의한 기타 정신장애",
        "amount": 26530644130
      },
      {
        "code": "AE11",
        "name": "2형 당뇨병",
        "amount": 24930059867
      },
      {
        "code": "AG31",
        "name": "달리 분류되지 않은 신경계통의 기타 퇴행성 질환",
        "amount": 19349458510
      },
      {
        "code": "AI67",
        "name": "기타 뇌혈관질환",
        "amount": 14733966302
      },
      {
        "code": "AE78",
        "name": "지질단백질대사장애 및 기타 지질증",
        "amount": 13266096166
      },
      {
        "code": "AG20",
        "name": "파킨슨병",
        "amount": 6996083573
      },
      {
        "code": "AI61",
        "name": "뇌내출혈",
        "amount": 5628152526
      },
      {
        "code": "AI65",
        "name": "뇌경색증을 유발하지 않은 뇌전동맥의 폐쇄 및 협착",
        "amount": 4491466679
      },
      {
        "code": "AG45",
        "name": "일과성 뇌허혈발작 및 관련 증후군",
        "amount": 4401689005
      }
    ]
  },
  "timeline": [
    {
      "date": "2020-08",
      "text": "콜린알포세레이트 본인부담률 30→80% 인상 (선별급여 전환)",
      "type": "active"
    },
    {
      "date": "2023-01",
      "text": "옥시라세탐 임상재평가 효과 입증 실패 (식약처)",
      "type": "active"
    },
    {
      "date": "2023-?",
      "text": "아세틸엘카르니틴 퇴출 (선별 종합)",
      "type": "terminal"
    },
    {
      "date": "2024-02",
      "text": "옥시라세탐 회수·폐기 명령 — 시장 퇴출",
      "type": "terminal"
    },
    {
      "date": "2024-03",
      "text": "콜린알포 환수 처분 취소 청구 대법원 패소 확정",
      "type": "active"
    },
    {
      "date": "2026-?",
      "text": "콜린알포 임상시험 제출기한 도래 (회사 회계 환수부채 인식)",
      "type": "active"
    }
  ],
  "notes": [
    "심평원 공개 웹통계 '성분의 상병별'에서 수집한 콜린알포세레이트 cmpn × 월 × 상병 자료.",
    "건강보험·조제기준만 (보험자구분=4, 조제기준=201). 의료급여·보훈·처방기준 별도.",
    "현재 화면은 2024년 우선 복구분이다. 2018~2025 전체 시계열은 같은 스크립트로 추가 수집 가능.",
    "상병코드 prefix 'A' 는 HIRA 내부 표기 — 보도 시엔 ICD-10 표준 코드로 변환(예: AI10→I10)."
  ]
};