"""심평원 의약품사용정보조회서비스 (data.go.kr 15047819) 엔드포인트 레지스트리.

활용가이드(Swagger UI) 에서 확인한 실제 명세를 반영.

  Base URL : https://apis.data.go.kr/B551182/msupUserInfoService1.2
  공통 필수: ServiceKey, numOfRows, pageNo, diagYm(YYYYMM)
  - insupTp     : 보험자구분 (0:전체, 4:건강보험, 5:의료급여, 7:보훈)
  - cpmdPrscTp  : 조제/처방 구분 (01:조제기준, 02:처방기준)

  의약품 단위 키 (operation 별로 다름):
    - meftDivNo  : 약효분류군번호 (예: 232=소화성궤양용제, 218=고혈압)
    - atcCd      : ATC 코드 (3단계 또는 4단계)
    - cmpnCd     : 주성분코드

  공간 단위:
    - sidoCd / sgguCd  : 시도/시군구 코드 (병원코드정보서비스>주소코드조회로 확인)
    - clCd             : 요양기관 종별 (상급종합/종합/병원/의원/약국 등)

응답 표준 스키마 (XML → 파싱):
  response.body.items.item (list 또는 dict).
  주요 필드:
    diagYm, insupTpCd, sidoCd, sidoCdNm, sgguCd, sgguCdNm,
    meftDivNo, meftDivNoNm, atcCd, atcCdNm, cmpnCd, cmpnCdNm,
    msupUseAmt(사용금액), totUseQty(사용량)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass(frozen=True)
class Endpoint:
    name: str
    operation: str
    required_params: tuple[str, ...] = ()
    page_key: str = "pageNo"
    rows_key: str = "numOfRows"
    service_key_param: str = "ServiceKey"  # 대문자 S 주의
    response_format: str = "xml"
    default_params: Dict[str, str] = field(default_factory=dict)
    note: str = ""


# 약효분류군 × 지역 (시도/시군구)
MEFT_DIV_AREA = Endpoint(
    name="meft_div_area",
    operation="getMeftDivAreaList1.2",
    required_params=(
        "diagYm",
        "meftDivNo",
        "insupTp",
        "cpmdPrscTp",
        "sidoCd",
        "sgguCd",
    ),
    note="H1·H4 분석용 메인 엔드포인트. 시군구별 약효분류군 사용량.",
)

# 약효분류군 × 요양기관 종별
MEFT_DIV_CL = Endpoint(
    name="meft_div_cl",
    operation="getMeftDivClList1.2",
    required_params=("diagYm", "meftDivNo", "insupTp", "cpmdPrscTp", "clCd"),
    note="시군구 차원이 없어 호출량이 적다 — H2 집중도/시계열 추세 추출에 우선 사용.",
)

# 4단계 ATC × 지역
ATC_STP4_AREA = Endpoint(
    name="atc4_area",
    operation="getAtcStp4AreaList1.2",
    required_params=("diagYm", "atcCd", "insupTp", "cpmdPrscTp", "sidoCd", "sgguCd"),
    note="국제 약효분류 ATC 4단계. 약가마스터와 직접 조인 가능.",
)

# 4단계 ATC × 의료기관 종별
ATC_STP4_CL = Endpoint(
    name="atc4_cl",
    operation="getAtcStp4ClList1.2",
    required_params=("diagYm", "atcCd", "insupTp", "cpmdPrscTp", "clCd"),
)

# 3단계 ATC × 지역
ATC_STP3_AREA = Endpoint(
    name="atc3_area",
    operation="getAtcStp3AreaList1.2",
    required_params=("diagYm", "atcCd", "insupTp", "cpmdPrscTp", "sidoCd", "sgguCd"),
)

# 3단계 ATC × 의료기관 종별
ATC_STP3_CL = Endpoint(
    name="atc3_cl",
    operation="getAtcStp3ClList1.2",
    required_params=("diagYm", "atcCd", "insupTp", "cpmdPrscTp", "clCd"),
)

# 성분별 × 지역  — 파라미터명 'gnlNmCd' (일반명코드) 주의. 응답도 gnlNmCd / gnlNmCdNm
CMPN_AREA = Endpoint(
    name="cmpn_area",
    operation="getCmpnAreaList1.2",
    required_params=("diagYm", "gnlNmCd", "insupTp", "cpmdPrscTp", "sidoCd", "sgguCd"),
    note="H3 / B 트랙. 성분별 시군구. gnlNmCd 예: 138101ACS = choline alfoscerate.",
)

# 성분별 × 의료기관 종별
CMPN_CL = Endpoint(
    name="cmpn_cl",
    operation="getCmpnClList1.2",
    required_params=("diagYm", "gnlNmCd", "insupTp", "cpmdPrscTp", "sidoCd", "sgguCd", "clCd"),
    note="H5 / C 트랙. 의원-병원 비교의 본 데이터.",
)

# 성분별 × 상병  — sickCd 가 옵션! 빼면 모든 상병 페이지네이션으로 반환
# (전국 합산. 응답에 sidoCd/sgguCd 없음)
CMPN_SICK = Endpoint(
    name="cmpn_sick",
    operation="getCmpnSickList1.2",
    required_params=("diagYm", "gnlNmCd", "insupTp", "cpmdPrscTp"),
    note="A 트랙. sickCd 빼면 한 콜에 200상병, 한 달 6콜로 완수. 응답 필드: st3SickSym, st3SickSymNm.",
)

# 약효분류군 × 상병
MEFT_DIV_SICK = Endpoint(
    name="meft_div_sick",
    operation="getMeftDivSickList1.2",
    required_params=("diagYm", "meftDivNo", "insupTp", "cpmdPrscTp"),
)

# 3/4단계 ATC × 상병
ATC_STP3_SICK = Endpoint(
    name="atc3_sick",
    operation="getAtcStp3SickList1.2",
    required_params=("diagYm", "atcCd", "insupTp", "cpmdPrscTp"),
)
ATC_STP4_SICK = Endpoint(
    name="atc4_sick",
    operation="getAtcStp4SickList1.2",
    required_params=("diagYm", "atcCd", "insupTp", "cpmdPrscTp"),
)


REGISTRY: Dict[str, Endpoint] = {
    ep.name: ep
    for ep in (
        MEFT_DIV_AREA,
        MEFT_DIV_CL,
        MEFT_DIV_SICK,
        ATC_STP3_AREA,
        ATC_STP3_CL,
        ATC_STP3_SICK,
        ATC_STP4_AREA,
        ATC_STP4_CL,
        ATC_STP4_SICK,
        CMPN_AREA,
        CMPN_CL,
        CMPN_SICK,
    )
}


def get(name: str) -> Endpoint:
    if name not in REGISTRY:
        raise KeyError(f"unknown endpoint: {name}. known: {list(REGISTRY)}")
    return REGISTRY[name]


# ----------------------------------------------------------------------
# 자주 쓰는 코드 상수
# ----------------------------------------------------------------------
INSUP_TP = {
    "all": "0",
    "건강보험": "4",
    "의료급여": "5",
    "보훈": "7",
}

CPMD_PRSC_TP = {
    "조제기준": "01",
    "처방기준": "02",
}

# 1차 탐사 우선순위 약효분류군 (3자리)
PRIORITY_MEFT_DIV = {
    "111": "전신마취제",
    "117": "정신신경용제",
    "218": "혈압강하제",
    "232": "소화성궤양용제",
    "239": "기타의 소화기관용약",
    "264": "통풍치료제",
    "321": "비타민A 및 D제",
    "333": "혈액응고저지제",
    "611": "주로 그람양성균에 작용하는 것 (항생제)",
    "612": "주로 그람음성균에 작용하는 것 (항생제)",
    "618": "주로 그람양성균,마이코플라즈마에 작용하는 것",
    "421": "항악성종양제",
    "117": "정신신경용제 (벤조 포함)",
}
