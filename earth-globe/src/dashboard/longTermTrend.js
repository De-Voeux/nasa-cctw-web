// Long-term change cards (2003–2024) for the region panel.
// Data: src/data/longTermTrends.json, built by
// data/seagis-nasa-extractor/scripts/build_trends.py from the monthly zone values
// (the same rows as seagis_monthly_metrics). The statistics are computed there, not here.

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c])
const ORDER = ["sst", "air_temp", "rain", "salinity", "ph", "nitrate", "phosphate"]

function niceStep(span, count) {
  const raw = span / Math.max(1, count)
  const mag = 10 ** Math.floor(Math.log10(raw))
  const n = raw / mag
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * mag
}
const decimalsFor = (step) => (String(+step.toFixed(10)).split(".")[1] || "").length
const median = (xs) => {
  const s = [...xs].sort((a, b) => a - b)
  const m = s.length
  return m % 2 ? s[(m - 1) / 2] : (s[m / 2 - 1] + s[m / 2]) / 2
}

/** "+0.31" with enough digits that a small slope does not print as 0. */
export function signed(v, digits) {
  const d = Math.max(digits, Math.abs(v) > 0 ? Math.min(6, Math.ceil(-Math.log10(Math.abs(v))) + 1) : digits)
  const s = v.toFixed(d)
  return v > 0 ? `+${s}` : s
}

/** Plain-language verdict and the numbers behind it. */
export function verdict(series) {
  const t = series.trend
  if (!t) return { tone: "none", label: "Not enough years to test", detail: "" }
  const unit = series.unit ? ` ${series.unit}` : ""
  const p = t.p < 0.001 ? "p < 0.001" : `p = ${t.p.toFixed(3)}`
  const slope = `${signed(t.slope_per_decade, series.digits)}${unit} per decade`
  const ci = t.ci95_per_decade
    ? ` (95% CI ${signed(t.ci95_per_decade[0], series.digits)} to ${signed(t.ci95_per_decade[1], series.digits)})`
    : ""
  const years = `${t.first_year}–${t.last_year}, ${t.n_years} years`
  if (!t.significant) return { tone: "flat", label: "No clear trend", detail: `${slope}${ci}, ${p} · ${years}` }
  return {
    tone: t.slope_per_decade > 0 ? "up" : "down",
    label: t.slope_per_decade > 0 ? "Rising" : "Falling",
    detail: `${slope}${ci}, ${p} · ${years}`,
  }
}

/** "Highest in May, lowest in Jan", from the monthly climatology. */
export function seasonLine(series) {
  const c = series.climatology || []
  const idx = c.map((v, i) => [v, i]).filter(([v]) => v != null)
  if (idx.length < 12) return ""
  const hi = idx.reduce((a, b) => (b[0] > a[0] ? b : a))
  const lo = idx.reduce((a, b) => (b[0] < a[0] ? b : a))
  const f = (v) => v.toFixed(series.digits)
  const unit = series.unit ? ` ${series.unit}` : ""
  return `Usually highest in ${MONTHS[hi[1]]} (${f(hi[0])}${unit}) and lowest in ${MONTHS[lo[1]]} (${f(lo[0])}${unit}).`
}

/**
 * Annual means as a line (gaps where a year is incomplete) with the Sen's slope line
 * drawn through the median intercept. Same chart classes as trendChart.js.
 */
export function longTermChart(series, years) {
  const H = 40
  const pts = years.map((y, i) => [y, series.annual[i]]).filter(([, v]) => v != null)
  if (pts.length < 2) return ""
  const t = series.trend
  const perYear = t ? t.slope_per_decade / 10 : null
  const b = t ? median(pts.map(([y, v]) => v - perYear * y)) : null
  const line = (y) => b + perYear * y
  const vals = pts.map(([, v]) => v)
  const fit = t ? [line(years[0]), line(years[years.length - 1])] : []
  let lo = Math.min(...vals, ...fit)
  let hi = Math.max(...vals, ...fit)
  const minSpan = 4 * 10 ** -series.digits
  if (hi - lo < minSpan) {
    const mid = (hi + lo) / 2
    lo = mid - minSpan / 2
    hi = mid + minSpan / 2
  }
  const step = niceStep(hi - lo, 3)
  lo = Math.floor(lo / step) * step
  hi = Math.ceil(hi / step) * step
  if (lo < 0 && Math.min(...vals) >= 0) lo = 0
  const yTicks = []
  for (let v = lo; v <= hi + step / 2; v += step) yTicks.push(+v.toFixed(10))
  const tickDigits = Math.min(5, decimalsFor(step))
  const y0 = years[0]
  const span = Math.max(1, years[years.length - 1] - y0)
  const X = (y) => ((y - y0) / span) * 100
  const Y = (v) => H - ((v - lo) / (hi - lo)) * H
  const pct = (v) => ((Y(v) / H) * 100).toFixed(2)

  // One polyline per run of consecutive complete years.
  const runs = []
  let run = []
  years.forEach((y, i) => {
    const v = series.annual[i]
    if (v == null) {
      if (run.length) runs.push(run)
      run = []
    } else run.push(`${X(y).toFixed(2)},${Y(v).toFixed(2)}`)
  })
  if (run.length) runs.push(run)
  const xTicks = [...new Set([y0, y0 + Math.round(span / 3), y0 + Math.round((2 * span) / 3), years[years.length - 1]])]
  const f = (v) => v.toFixed(series.digits)
  const label = `${series.name}, annual mean ${pts[0][0]} to ${pts[pts.length - 1][0]}: ${f(pts[0][1])} to ${f(pts[pts.length - 1][1])} ${series.unit}.`

  return `
  <figure class="trend lt-trend" role="img" aria-label="${esc(label)}">
    <span class="trend-unit" aria-hidden="true">${esc(series.unit)}</span>
    <div class="trend-y" aria-hidden="true">${yTicks.map((v) => `<span style="top:${pct(v)}%">${v.toFixed(tickDigits)}</span>`).join("")}</div>
    <div class="trend-plot" aria-hidden="true">
      <svg viewBox="0 0 100 ${H}" preserveAspectRatio="none">
        ${yTicks.map((v) => `<line class="t-grid" x1="0" x2="100" y1="${Y(v).toFixed(2)}" y2="${Y(v).toFixed(2)}"/>`).join("")}
        ${runs.map((r) => (r.length > 1 ? `<polyline class="t-annual" points="${r.join(" ")}"/>` : "")).join("")}
        ${t ? `<line class="t-sen${t.significant ? " sig" : ""}" x1="0" x2="100" y1="${Y(fit[0]).toFixed(2)}" y2="${Y(fit[1]).toFixed(2)}"/>` : ""}
      </svg>
      ${pts.map(([y, v]) => `<span class="t-pt" style="left:${X(y).toFixed(2)}%;top:${pct(v)}%"></span>`).join("")}
    </div>
    <div class="trend-x" aria-hidden="true">${xTicks
      .map((y, k) => `<span class="${k === 0 ? "first" : k === xTicks.length - 1 ? "last" : ""}" style="left:${X(y)}%">${y}</span>`)
      .join("")}</div>
    <figcaption class="trend-legend">
      <span><i class="k-annual"></i>Yearly average</span>
      ${t ? `<span><i class="k-sen"></i>Trend (Sen's slope)</span>` : ""}
    </figcaption>
  </figure>`
}

/** The whole "Long-term change" section for one data region, or "" when there is none. */
export function longTermSection(doc, regionId) {
  const region = regionId ? doc?.regions?.[regionId] : null
  if (!region) return ""
  const keys = ORDER.filter((k) => region.series[k])
  if (!keys.length) return ""
  const y0 = doc.years[0]
  const y1 = doc.years[doc.years.length - 1]
  const cards = keys.map((k) => {
    const s = region.series[k]
    const v = verdict(s)
    const season = seasonLine(s)
    return `
    <details class="driver lt-card">
      <summary>
        <span class="lt-name">${esc(s.name)}</span>
        <span class="lt-badge lt-${v.tone}">${esc(v.label)}</span>
      </summary>
      ${longTermChart(s, doc.years)}
      ${v.detail ? `<p class="lt-detail">${esc(v.detail)}</p>` : ""}
      ${season ? `<p class="lt-detail">${esc(season)}</p>` : ""}
      <p class="driver-src">Data: ${esc(s.source)}${s.product_version ? ` · ${esc(s.product_version)}` : ""}</p>
    </details>`
  })
  return `
    <h2 class="section-title">Long-term change, ${y0}–${y1}</h2>
    <p class="muted small lt-intro">Yearly averages for this area. A trend counts as clear when the Mann-Kendall test gives p &lt; 0.05. These are satellite and model values for the wider area, not measurements at a farm, and a trend in the water is not a sign the seaweed is sick.</p>
    ${cards.join("")}`
}
