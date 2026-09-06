#!/usr/bin/env python3
"""choline_sick.parquet → 강의용 시각화 케이스스터디 HTML 생성.
데이터가 갱신되면(시계열 추가 등) 다시 돌리면 차트가 갱신된다.

사용:
  python3 build_case_study.py <parquet_path> <out_html>
"""
import sys, json, html
import pandas as pd

CORE_PRE = ("AF00", "AF01", "AF02", "AF03", "AG30")
EOK = 1e8

def won(v):  # 원 → 억 문자열
    return f"{v/EOK:,.0f}억"

def cat_of(c):
    c = str(c)
    if c.startswith(CORE_PRE): return "치매 핵심(F00-03·G30)"
    if c.startswith(("AI6", "AI7", "AG45")): return "뇌혈관·순환기"
    if c.startswith(("AI10","AI11","AI12","AI13","AI15")): return "고혈압·심혈관"
    if c.startswith(("AE0","AE1","AE7","AE8")): return "대사(당뇨·지질)"
    if c.startswith(("AF","AG2","AG3","AG4","AG9","AR")): return "정신·기타신경"
    return "기타"

def bar_chart(rows, unit_max, width=560, bh=30, gap=14, color="#5b9dff"):
    """rows: list of (label, value, sublabel, is_core). 가로 막대 SVG."""
    h = len(rows)*(bh+gap)+10
    labelw = 210
    barw = width-labelw-95
    out = [f'<svg viewBox="0 0 {width} {h}" width="100%" role="img">']
    for i,(lab,val,sub,core) in enumerate(rows):
        y=i*(bh+gap)+6
        w=max(2,barw*val/unit_max)
        col = "#4fd18b" if core else color
        out.append(f'<text x="0" y="{y+bh*0.62}" fill="#c7cdd8" font-size="13">{html.escape(lab)}</text>')
        out.append(f'<rect x="{labelw}" y="{y}" width="{w:.1f}" height="{bh}" rx="6" fill="{col}"/>')
        out.append(f'<text x="{labelw+w+8:.1f}" y="{y+bh*0.62}" fill="#e8eaed" font-size="12.5" font-weight="600">{html.escape(sub)}</text>')
    out.append('</svg>')
    return "\n".join(out)

def donut(core_pct):
    import math
    r=70; c=2*math.pi*r; noncore=100-core_pct
    off=c*core_pct/100
    return f'''<svg viewBox="0 0 200 200" width="200" height="200">
      <circle cx="100" cy="100" r="{r}" fill="none" stroke="#4fd18b" stroke-width="34"/>
      <circle cx="100" cy="100" r="{r}" fill="none" stroke="#ff6b6b" stroke-width="34"
        stroke-dasharray="{c*noncore/100:.1f} {c:.1f}" stroke-dashoffset="{-off:.1f}"
        transform="rotate(-90 100 100)"/>
      <text x="100" y="94" text-anchor="middle" fill="#ff6b6b" font-size="30" font-weight="800">{noncore:.1f}%</text>
      <text x="100" y="116" text-anchor="middle" fill="#9aa3b2" font-size="12">치매코드 밖</text>
    </svg>'''

def line_chart(pairs, width=620, h=190):
    """pairs: list of (label, value). 선 그래프."""
    if not pairs: return ""
    vals=[v for _,v in pairs]; mx=max(vals); mn=min(vals)*0.9
    n=len(pairs); padL=48; padR=16; padT=14; padB=28
    pw=width-padL-padR; ph=h-padT-padB
    def x(i): return padL+pw*i/max(1,n-1)
    def y(v): return padT+ph*(1-(v-mn)/(mx-mn if mx>mn else 1))
    pts=" ".join(f"{x(i):.1f},{y(v):.1f}" for i,(_,v) in enumerate(pairs))
    dots="".join(f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="3.2" fill="#5b9dff"/>' for i,(_,v) in enumerate(pairs))
    labs="".join(f'<text x="{x(i):.1f}" y="{h-8}" text-anchor="middle" fill="#9aa3b2" font-size="10">{html.escape(l)}</text>'
                 for i,(l,_) in enumerate(pairs) if i%max(1,n//8)==0 or i==n-1)
    return f'''<svg viewBox="0 0 {width} {h}" width="100%">
      <polyline points="{pts}" fill="none" stroke="#5b9dff" stroke-width="2.5"/>
      {dots}{labs}
      <text x="4" y="{y(mx):.1f}" fill="#6b7280" font-size="10">{won(mx)}</text>
    </svg>'''

def stacked_bars(years, core, noncore, width=620, h=230):
    """연도별 치매핵심(초록)+비치매(빨강) 누적 막대."""
    n=len(years); mx=max(c+nc for c,nc in zip(core,noncore))
    padL=44; padR=14; padT=14; padB=26
    pw=width-padL-padR; ph=h-padT-padB
    bw=pw/n*0.62; step=pw/n
    out=[f'<svg viewBox="0 0 {width} {h}" width="100%">']
    def yc(v): return padT+ph*(1-v/mx)
    for i,(c,nc) in enumerate(zip(core,noncore)):
        cx=padL+step*i+step*0.19
        hnc=ph*nc/mx; hc=ph*c/mx
        out.append(f'<rect x="{cx:.1f}" y="{yc(c+nc):.1f}" width="{bw:.1f}" height="{hnc:.1f}" fill="#ff6b6b"/>')
        out.append(f'<rect x="{cx:.1f}" y="{yc(c):.1f}" width="{bw:.1f}" height="{hc:.1f}" fill="#4fd18b"/>')
        out.append(f'<text x="{cx+bw/2:.1f}" y="{h-8}" text-anchor="middle" fill="#9aa3b2" font-size="10">{years[i][2:]}</text>')
    out.append(f'<text x="4" y="{padT+8}" fill="#6b7280" font-size="10">{won(mx)}</text>')
    out.append('</svg>')
    return "\n".join(out)

def multiline(years, series, width=620, h=250):
    """series: list of (label, values[], color). 공유 스케일 다중선 + 범례."""
    n=len(years); mx=max(max(v) for _,v,_ in series)
    padL=44; padR=14; padT=14; padB=26
    pw=width-padL-padR; ph=h-padT-padB
    def x(i): return padL+pw*i/max(1,n-1)
    def y(v): return padT+ph*(1-v/mx)
    out=[f'<svg viewBox="0 0 {width} {h}" width="100%">']
    for lab,vals,col in series:
        pts=" ".join(f"{x(i):.1f},{y(v):.1f}" for i,v in enumerate(vals))
        out.append(f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="2.2"/>')
        out.append(f'<text x="{x(n-1)+3:.1f}" y="{y(vals[-1]):.1f}" fill="{col}" font-size="9.5">{html.escape(lab.split()[0])}</text>')
    for i in range(n):
        if i%2==0 or i==n-1:
            out.append(f'<text x="{x(i):.1f}" y="{h-8}" text-anchor="middle" fill="#9aa3b2" font-size="10">{years[i][2:]}</text>')
    out.append(f'<text x="4" y="{padT+8}" fill="#6b7280" font-size="10">{won(mx)}</text>')
    out.append('</svg>')
    return "\n".join(out)

def main():
    pq = sys.argv[1] if len(sys.argv)>1 else "data/processed/choline_sick.parquet"
    out = sys.argv[2] if len(sys.argv)>2 else "dashboard/case_study.html"
    df = pd.read_parquet(pq)
    df["sick_cd"]=df["sick_cd"].astype(str)
    df["y"]=df.period.astype(str).str[:4]
    years = sorted(df.y.unique())
    latest=years[-1]

    # 연도별 추이 = 전체 연도
    yr = df.groupby("y").claim_amount.sum().sort_index()
    yearly = [(y, int(v)) for y,v in yr.items()]

    # 연도별 치매핵심 vs 비치매
    df["is_core"]=df.sick_cd.str.startswith(CORE_PRE)
    yc = df.groupby(["y","is_core"]).claim_amount.sum().unstack(fill_value=0).sort_index()
    yc_core=[int(yc.loc[y].get(True,0)) for y in years]
    yc_non=[int(yc.loc[y].get(False,0)) for y in years]
    noncore_share=[nc/(c+nc)*100 for c,nc in zip(yc_core,yc_non)]

    # 주요 상병(최신연도 상위 6) 연도별 추이
    PAL=["#ff6b6b","#4fd18b","#5b9dff","#ffb454","#c084fc","#22d3ee"]
    top6=df[df.y==latest].groupby(["sick_cd","sick_name"]).claim_amount.sum().sort_values(ascending=False).head(6)
    tl_series=[]
    for j,((cd,nm),_) in enumerate(top6.items()):
        vals=[int(df[(df.y==y)&(df.sick_cd==cd)].claim_amount.sum()) for y in years]
        icd=cd[1:] if cd and cd[0]=="A" else cd
        tl_series.append((f"{icd} {nm[:9]}", vals, PAL[j%len(PAL)]))

    # 스냅샷 지표(도넛·카테고리·상위상병·월별·KPI)는 최신연도 기준
    dfl = df[df.y==latest]
    tot = dfl.claim_amount.sum()
    core = dfl[dfl.sick_cd.str.startswith(CORE_PRE)].claim_amount.sum()
    core_pct = core/tot*100

    # 월별 (최신 연도)
    mon = dfl.groupby("period").claim_amount.sum().sort_index()
    monthly=[(p[4:6]+"월", int(v)) for p,v in mon.items()]

    # 카테고리 (최신 연도)
    dfl=dfl.assign(cat=dfl.sick_cd.map(cat_of))
    cats=dfl.groupby("cat").claim_amount.sum().sort_values(ascending=False)
    cat_rows=[(k, int(v), won(v), k.startswith("치매")) for k,v in cats.items()]
    cat_max=max(v for _,v,_,_ in cat_rows)

    # 상위 상병 (최신 연도)
    top=dfl.groupby(["sick_cd","sick_name"]).claim_amount.sum().sort_values(ascending=False).head(10)
    core_set=set()
    top_rows=[]
    for (cd,nm),v in top.items():
        iscore=cd.startswith(CORE_PRE)
        icd=cd[1:] if cd and cd[0]=="A" else cd
        top_rows.append((f"{icd} {nm[:16]}", int(v), won(v), iscore))
    top_max=max(v for _,v,_,_ in top_rows)

    multiyear = len(years)>1
    growth = yearly[-1][1]/yearly[0][1] if yearly and yearly[0][1] else 0
    y2020 = dict(yearly).get("2020"); y2019 = dict(yearly).get("2019")
    ts_section = ""
    if multiyear:
        yoy2020 = f"(전년比 +{(y2020/y2019-1)*100:.0f}%)" if y2020 and y2019 else ""
        tl_legend="".join(f'<span class="chip2"><span class="sw" style="background:{col}"></span>{html.escape(lab)}</span>' for lab,_,col in tl_series)
        ts_section = f'''<h2><span class="n">3</span>연도별 청구액 추이 <span class="ok">✓ {years[0]}–{years[-1]}</span></h2>
        <div class="card">{line_chart([(y[2:],v) for y,v in yearly])}
        <p><b>{years[0]} {won(yearly[0][1])} → {latest} {won(yearly[-1][1])}, {growth:.1f}배.</b>
        2020년 8월 정부가 "치매 외 효능 근거 미흡"으로 본인부담을 30→80%로 올렸지만, 그해 청구는 오히려 {won(y2020) if y2020 else ''} {yoy2020}로 늘었고 이후로도 꺾이지 않았다.</p>
        <p class="muted">재평가가 청구 규모를 줄였다는 근거는 이 곡선에서 보이지 않는다 — 정책효과에 대한 질문의 출발점.</p></div>

        <h2><span class="n">4</span>치매 vs 비치매, 10년 내내 벌어진 격차</h2>
        <div class="card">{stacked_bars(years, yc_core, yc_non)}
        <p><span class="sw" style="background:#ff6b6b"></span><b>비치매</b> {won(yc_non[0])}→{won(yc_non[-1])} &nbsp;·&nbsp;
        <span class="sw" style="background:#4fd18b"></span><b>치매 핵심</b> {won(yc_core[0])}→{won(yc_core[-1])}</p>
        <p class="muted">비치매 비중은 {noncore_share[0]:.0f}%(2015)→{noncore_share[-1]:.0f}%({latest})로 10년 내내 <b>약 90%에 고착</b>. 치매약이지만 청구의 대부분은 줄곧 치매 밖에 있었다.</p></div>

        <h2><span class="n">5</span>상병별 청구액 추이 — 고혈압이 알츠하이머를 앞질렀다</h2>
        <div class="card">{multiline(years, tl_series)}
        <div style="margin-top:8px">{tl_legend}</div>
        <p class="muted">2024 상위 6개 상병의 연도별 청구액. <span class="badc">본태성 고혈압(I10, 빨강)</span>이 가장 가파르게 올라 실제 적응증인 <span class="good">알츠하이머(F00, 초록)</span>를 2019년경 추월했다.</p></div>'''
    else:
        ts_section = f'''<h2><span class="n">3</span>연도별 청구액 추이 <span class="pending">⏳ {latest}만 수집됨 — 2015~2023 추가 예정</span></h2>
        <div class="card pending-card">
        <p>현재 <b>{latest}년 단년</b>만 확보돼 시계열 그래프는 아직 그릴 수 없다. 크롤러로 과거 연도를 수집하면 이 자리에 "재평가(2020) 전후 추이"가 채워진다.</p>
        <p class="muted">참고용 과거 단편: 2021년 약 3,099억 → {latest}년 {won(tot)} (성분코드 범위에 따라 값이 달라지므로 동일 코드셋으로 재수집해 비교할 것).</p>
        </div>'''

    doc = f'''<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>콜린알포세레이트 청구 구조 — 강의 케이스스터디</title>
<style>
:root{{--bg:#0f1115;--panel:#171a21;--line:#2a2f3a;--ink:#e8eaed;--muted:#9aa3b2;--accent:#5b9dff;--good:#4fd18b;--bad:#ff6b6b;--warn:#ffb454;--chip:#232936}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Pretendard",system-ui,sans-serif;line-height:1.6}}
.wrap{{max-width:900px;margin:0 auto;padding:30px 20px 80px}}
header{{border-bottom:1px solid var(--line);padding-bottom:18px}}
.eyebrow{{color:var(--accent);font-size:12px;font-weight:700;letter-spacing:.14em;text-transform:uppercase}}
h1{{font-size:27px;margin:8px 0 6px;font-weight:800;letter-spacing:-.01em}}
.sub{{color:var(--muted);font-size:14px}}
h2{{font-size:19px;margin:40px 0 14px;font-weight:800;display:flex;align-items:center;gap:9px;flex-wrap:wrap}}
h2 .n{{display:inline-flex;width:26px;height:26px;border-radius:8px;background:var(--chip);color:var(--accent);font-size:13px;align-items:center;justify-content:center;font-weight:700}}
.ok{{font-size:12px;color:var(--good);font-weight:600}} .pending{{font-size:12px;color:var(--warn);font-weight:600}}
.kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:22px 0 4px}}
.kpi{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px}}
.kpi .v{{font-size:23px;font-weight:800;letter-spacing:-.02em}}
.kpi .l{{color:var(--muted);font-size:12px;margin-top:4px;line-height:1.4}}
.kpi.bad .v{{color:var(--bad)}} .kpi.warn .v{{color:var(--warn)}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px 20px;margin:12px 0}}
.pending-card{{border-color:#5a4a25;background:#1d1a12}}
.donut-wrap{{display:flex;gap:24px;align-items:center;flex-wrap:wrap}}
.legend{{font-size:13px;color:var(--muted)}} .legend b{{color:var(--ink)}}
.sw{{display:inline-block;width:11px;height:11px;border-radius:3px;margin-right:6px;vertical-align:middle}}
.chip2{{display:inline-block;background:var(--chip);border:1px solid var(--line);border-radius:999px;padding:3px 10px;font-size:12px;color:#c7cdd8;margin:3px 5px 0 0}}
.muted{{color:var(--muted);font-size:13px}} .good{{color:var(--good)}} .badc{{color:var(--bad)}}
ul{{margin:8px 0;padding-left:20px}} li{{margin:5px 0}}
.two{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}
.foot{{margin-top:44px;padding-top:18px;border-top:1px solid var(--line);color:var(--muted);font-size:12.5px}}
code{{background:#0a0c10;border:1px solid var(--line);border-radius:5px;padding:1px 6px;font-size:12.5px}}
@media(max-width:640px){{.kpis{{grid-template-columns:repeat(2,1fr)}}.two{{grid-template-columns:1fr}}}}
</style></head><body><div class="wrap">
<header>
<div class="eyebrow">HIRA Case Study · 강의용</div>
<h1>콜린알포세레이트, 청구는 어디로 갔나</h1>
<div class="sub">심평원 공개 상병별 통계 · 건강보험·조제기준 · 3개 경구제(캡슐·연질캡슐·정제) · {years[0]}~{latest} · 생성 {pd.Timestamp.now():%Y-%m-%d}</div>
</header>

<div class="kpis">
<div class="kpi"><div class="v">{won(tot)}</div><div class="l">{latest} 총 청구액<br>(수집분)</div></div>
<div class="kpi bad"><div class="v">{100-core_pct:.1f}%</div><div class="l">치매 핵심코드<br><b>밖</b>에서 발생</div></div>
<div class="kpi warn"><div class="v">I10</div><div class="l">금액 1위 상병<br>본태성 고혈압</div></div>
<div class="kpi"><div class="v">{df.sick_cd.nunique()}개</div><div class="l">청구된<br>상병 종류</div></div>
</div>
<p class="muted">※ 청구 상병 ≠ 처방 목적. 아래 숫자는 "정책 판단과 청구 구조의 괴리"를 보여주는 신호이지 부정의 증거가 아니다.</p>

<h2><span class="n">1</span>치매약인데, 치매코드 밖이 {100-core_pct:.0f}%</h2>
<div class="card"><div class="donut-wrap">
{donut(core_pct)}
<div class="legend">
<p><span class="sw" style="background:#ff6b6b"></span><b>비핵심 {won(tot-core)}</b> ({100-core_pct:.1f}%) — 고혈압·뇌경색·당뇨 등</p>
<p><span class="sw" style="background:#4fd18b"></span><b>치매 핵심 {won(core)}</b> ({core_pct:.1f}%) — F00·F01·F02·F03·G30</p>
<p class="muted">2020년 정부는 "치매 외 효능 근거 미흡"으로 본인부담을 올렸다. 그런데 청구의 {100-core_pct:.0f}%는 여전히 치매 핵심코드 밖에 있다.</p>
</div></div></div>

<h2><span class="n">2</span>상병 대분류별 청구액</h2>
<div class="card">{bar_chart(cat_rows, cat_max)}
<p class="muted">치매 핵심(초록)은 6개 그룹 중 5위. 정신·기타신경, 뇌혈관, 고혈압·심혈관이 앞선다.</p></div>

{ts_section}

<h2><span class="n">6</span>{latest} 금액 상위 10개 상병</h2>
<div class="card">{bar_chart(top_rows, top_max)}
<p class="muted">초록 = 치매 핵심코드. 1위는 알츠하이머가 아니라 <span class="badc">고혈압(I10)</span>.</p></div>

<h2><span class="n">7</span>{latest} 월별 청구액</h2>
<div class="card">{line_chart(monthly)}
<p class="muted">연중 월 2,900~3,200억 수준으로 고르게 유지 — 특정 시기 급증이 아닌 상시 처방 구조.</p></div>

<h2><span class="n">8</span>강의 포인트 — 말할 수 있음 vs 위험함</h2>
<div class="two">
<div class="card"><h3 class="good" style="margin-top:0">말할 수 있음</h3><ul>
<li>청구 상병 기준 비치매 코드의 금액 비중이 크다.</li>
<li>급여 재평가 취지와 실제 청구 구조 사이에 괴리가 보인다.</li>
<li>제품·회사·기관 자료가 확보되면 책임 소재를 좁힐 수 있다.</li></ul></div>
<div class="card"><h3 class="badc" style="margin-top:0">아직 위험함</h3><ul>
<li>"의사가 효과 없는 약을 알고도 처방했다."</li>
<li>"고혈압 치료 목적으로 콜린알포를 썼다."</li>
<li>"특정 회사가 재정누수를 만들었다."</li></ul></div>
</div>

<div class="foot">
공개자료 기반 실습·취재용. 의료적 효능·개별 처방 적정성·특정 회사의 법적 책임은 공개 통계만으로 단정하지 않는다.
상병코드 prefix <code>A</code>는 심평원 내부 표기 — 보도 시 ICD-10 표준(AI10→I10)으로 변환. 데이터: 심평원 성분의 상병별 사용실적, 보험자구분=4, 조제기준=201.
</div>
</div></body></html>'''

    with open(out, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"saved {out}  (years={years}, tot={won(tot)}, noncore={100-core_pct:.1f}%)")

if __name__ == "__main__":
    main()
