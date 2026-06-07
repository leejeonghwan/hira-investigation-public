(function () {
  const data = window.SUSPECT_DATA || { drugs: [], series: {}, sickByDrug: {}, kpis: {}, notes: [], timeline: [] };
  const colors = {
    palette: ["#177d72", "#4f5aa8", "#c87816", "#b64b5a", "#4e8b46", "#7b5a9e", "#1c8aa6", "#a85f2d", "#5b6f8a"],
    text: "#1d2422",
    muted: "#68716d",
    line: "#dce2dc",
  };
  const state = { drugFocus: data.drugs[0]?.key || null };

  const el = (id) => document.querySelector("#" + id);

  function won(v) {
    if (v == null || isNaN(v)) return "-";
    if (Math.abs(v) >= 1e11) return `${(v / 1e8).toLocaleString("ko-KR", { maximumFractionDigits: 0 })}억원`;
    if (Math.abs(v) >= 1e8) return `${(v / 1e8).toLocaleString("ko-KR", { maximumFractionDigits: 1 })}억원`;
    return `${v.toLocaleString("ko-KR")}원`;
  }
  function pct(v) { return v == null ? "-" : `${(v * 100).toLocaleString("ko-KR", { maximumFractionDigits: 1 })}%`; }
  function num(v) { return v == null ? "-" : v.toLocaleString("ko-KR"); }
  function colorFor(i) { return colors.palette[i % colors.palette.length]; }

  function canvasCtx(c) {
    const ratio = window.devicePixelRatio || 1;
    const cssH = +c.getAttribute("height") || 320;
    c.style.height = cssH + "px";
    const w = c.getBoundingClientRect().width;
    c.width = Math.max(1, Math.floor(w * ratio));
    c.height = Math.max(1, Math.floor(cssH * ratio));
    const ctx = c.getContext("2d");
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    return { ctx, w, h: cssH };
  }

  function roundRect(ctx, x, y, w, h, r) {
    const rr = Math.min(r, Math.abs(w) / 2, Math.abs(h) / 2);
    ctx.beginPath();
    ctx.moveTo(x + rr, y);
    ctx.arcTo(x + w, y, x + w, y + h, rr);
    ctx.arcTo(x + w, y + h, x, y + h, rr);
    ctx.arcTo(x, y + h, x, y, rr);
    ctx.arcTo(x, y, x + w, y, rr);
    ctx.closePath();
  }

  function renderKpis() {
    el("generatedAt").textContent = `생성 ${data.generatedAt || "-"}`;
    el("progressLabel").textContent = data.runStatus ? `상태: ${data.runStatus}` : "";
    el("kpiProgress").textContent = pct(data.kpis.overallProgress);
    el("kpiRows").textContent = num(data.kpis.totalRows);
    el("kpiAmount").textContent = won(data.kpis.amount2024);
    el("kpiSicks").textContent = num(data.kpis.totalSicks);
    el("notesList").innerHTML = (data.notes || []).map(n => `<li>${n}</li>`).join("");
  }

  function renderDrugStatus() {
    const rows = data.drugs.map((d, i) => {
      const cls = d.status === "complete" ? "status--complete"
        : d.status === "partial" ? "status--partial"
        : d.status === "missing" ? "status--missing" : "status--pending";
      const label = d.status === "complete" ? "완료"
        : d.status === "partial" ? "부분"
        : d.status === "missing" ? "코드없음" : "대기";
      const pctVal = d.progress != null ? Math.round(d.progress * 100) : 0;
      return `<tr>
        <td><span class="swatch" style="background:${colorFor(i)};vertical-align:middle"></span> ${d.key}</td>
        <td>${d.korName || "-"}</td>
        <td>${d.nCmpns ?? 0}</td>
        <td class="numeric">${d.completed ?? 0} / ${d.expected ?? 0}</td>
        <td><div class="progress-bar"><div class="progress-bar__fill" style="width:${pctVal}%"></div></div></td>
        <td><span class="status ${cls}">${label}</span></td>
      </tr>`;
    }).join("");
    el("drugStatusRows").innerHTML = rows;
  }

  function renderSeries() {
    const canvas = el("seriesCanvas");
    const { ctx, w, h } = canvasCtx(canvas);
    ctx.clearRect(0, 0, w, h);
    const pad = { top: 18, right: 18, bottom: 36, left: 70 };
    const cw = w - pad.left - pad.right;
    const ch = h - pad.top - pad.bottom;
    const years = data.series.years || [];
    if (!years.length) {
      ctx.fillStyle = colors.muted;
      ctx.font = "13px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("아직 데이터 없음 — 크롤이 시작되면 자동 표시", w / 2, h / 2);
      return;
    }
    const maxV = Math.max(0.1, ...(data.series.maxByYear || [1]));
    // grid
    ctx.strokeStyle = colors.line;
    ctx.fillStyle = colors.muted;
    ctx.font = "11px sans-serif";
    ctx.textAlign = "right";
    for (let i = 0; i <= 4; i++) {
      const y = pad.top + ch * (i / 4);
      ctx.beginPath();
      ctx.moveTo(pad.left, y);
      ctx.lineTo(w - pad.right, y);
      ctx.stroke();
      ctx.fillText(won(maxV * (1 - i / 4)), pad.left - 6, y + 3);
    }
    // x ticks
    ctx.textAlign = "center";
    years.forEach((yr, i) => {
      const x = pad.left + (cw * i) / Math.max(1, years.length - 1);
      ctx.fillText(yr, x, h - 14);
    });
    // policy markers
    const markers = data.series.markers || [];
    markers.forEach(m => {
      const idx = years.indexOf(m.year);
      if (idx < 0) return;
      const x = pad.left + (cw * idx) / Math.max(1, years.length - 1);
      ctx.strokeStyle = "#c87816";
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(x, pad.top);
      ctx.lineTo(x, pad.top + ch);
      ctx.stroke();
      ctx.setLineDash([]);
    });
    // lines
    (data.drugs || []).forEach((d, di) => {
      const vals = (data.series.byDrug || {})[d.key] || [];
      if (!vals.length) return;
      ctx.strokeStyle = colorFor(di);
      ctx.lineWidth = 2;
      ctx.beginPath();
      vals.forEach((v, i) => {
        const x = pad.left + (cw * i) / Math.max(1, years.length - 1);
        const y = pad.top + ch * (1 - Math.min(1, v / maxV));
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      });
      ctx.stroke();
    });
    // legend
    el("seriesLegend").innerHTML = (data.drugs || [])
      .map((d, i) => `<div class="legend__item"><span class="swatch" style="background:${colorFor(i)}"></span>${d.key}</div>`)
      .join("");
  }

  function drawHBars(canvas, items, label, value, max) {
    const { ctx, w, h } = canvasCtx(canvas);
    ctx.clearRect(0, 0, w, h);
    if (!items.length) {
      ctx.fillStyle = colors.muted;
      ctx.font = "13px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("데이터 없음", w / 2, h / 2);
      return;
    }
    const top = items.slice(0, 12);
    const mx = max != null ? max : Math.max(1, ...top.map(value));
    const pad = { top: 8, right: 16, bottom: 8, left: 130 };
    const rh = (h - pad.top - pad.bottom) / top.length;
    ctx.font = "12px sans-serif";
    top.forEach((row, i) => {
      const y = pad.top + i * rh;
      const v = value(row);
      const bw = ((w - pad.left - pad.right) * v) / mx;
      ctx.fillStyle = colors.text;
      ctx.textAlign = "right";
      const lab = label(row);
      ctx.fillText(lab.length > 18 ? lab.slice(0, 17) + "…" : lab, pad.left - 8, y + rh * 0.6);
      ctx.fillStyle = "#eef2ed";
      roundRect(ctx, pad.left, y + 4, w - pad.left - pad.right, Math.max(8, rh - 8), 4);
      ctx.fill();
      ctx.fillStyle = colorFor(i);
      roundRect(ctx, pad.left, y + 4, bw, Math.max(8, rh - 8), 4);
      ctx.fill();
      ctx.fillStyle = colors.text;
      ctx.textAlign = "left";
      const labelVal = v > 1e8 ? `${(v / 1e8).toLocaleString("ko-KR", { maximumFractionDigits: 1 })}억` : v.toLocaleString("ko-KR");
      ctx.fillText(labelVal, pad.left + Math.min(bw + 6, w - pad.left - 60), y + rh * 0.6);
    });
  }

  function renderAmounts() {
    const rows = (data.drugs || []).map(d => ({
      key: d.key,
      amount: (data.kpis?.amountByDrug || {})[d.key] || 0,
    })).sort((a, b) => b.amount - a.amount);
    drawHBars(el("amountCanvas"), rows, r => r.key, r => r.amount);
  }

  function renderSicks() {
    const rows = (data.drugs || []).map(d => ({
      key: d.key,
      sicks: (data.kpis?.sicksByDrug || {})[d.key] || 0,
    })).sort((a, b) => b.sicks - a.sicks);
    drawHBars(el("sicksCanvas"), rows, r => r.key, r => r.sicks);
  }

  function renderSickPicker() {
    const sel = el("drugSelect");
    sel.innerHTML = (data.drugs || []).map(d => `<option value="${d.key}">${d.key}</option>`).join("");
    if (state.drugFocus) sel.value = state.drugFocus;
    sel.addEventListener("change", () => { state.drugFocus = sel.value; renderSicknessChart(); });
    renderSicknessChart();
  }

  function renderSicknessChart() {
    const list = (data.sickByDrug || {})[state.drugFocus] || [];
    drawHBars(el("sicknessCanvas"), list, r => `${r.code} ${r.name || ""}`, r => r.amount);
  }

  function renderTimeline() {
    const items = data.timeline || [];
    el("timelineList").innerHTML = items.map(it => {
      const cls = it.type === "terminal" ? "terminal" : it.type === "active" ? "active" : "";
      return `<li class="${cls}"><span class="date">${it.date}</span>${it.text}</li>`;
    }).join("");
  }

  function init() {
    renderKpis();
    renderDrugStatus();
    renderSeries();
    renderAmounts();
    renderSicks();
    renderSickPicker();
    renderTimeline();
    window.addEventListener("resize", () => {
      window.requestAnimationFrame(() => {
        renderSeries(); renderAmounts(); renderSicks(); renderSicknessChart();
      });
    });
  }
  init();
})();
