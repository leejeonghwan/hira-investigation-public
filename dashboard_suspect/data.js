window.SUSPECT_DATA = {
  "generatedAt": "DEMO",
  "runStatus": "데모 — 자체 데이터로 build_data 실행 시 갱신",
  "drugs": [
    {"key": "drug_a", "korName": "약물 A (예시)", "nCmpns": 3, "completed": 360, "expected": 360, "progress": 1, "status": "complete"},
    {"key": "drug_b", "korName": "약물 B (예시)", "nCmpns": 2, "completed": 120, "expected": 240, "progress": 0.5, "status": "partial"}
  ],
  "series": {"years": ["2015","2016","2017","2018","2019","2020","2021","2022","2023","2024"],
    "byDrug": {"drug_a": [100,120,140,180,220,260,310,360,420,480], "drug_b": [50,60,70,90,110,130,160,200,260,320]},
    "maxByYear": [100,120,140,180,220,260,310,360,420,480],
    "markers": [{"year":"2020"}]},
  "kpis": {"overallProgress": 0.75, "totalRows": 50000, "amount2024": 80000000000, "totalSicks": 800,
    "amountByDrug": {"drug_a": 48000000000, "drug_b": 32000000000},
    "sicksByDrug": {"drug_a": 500, "drug_b": 300}},
  "sickByDrug": {},
  "timeline": [{"date":"2020","text":"예시 정책 이벤트","type":"active"}],
  "notes": ["데모 데이터입니다. 실제 데이터는 본인의 HIRA OpenAPI 키로 직접 수집하세요."]
};
