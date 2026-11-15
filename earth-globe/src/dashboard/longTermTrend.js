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
    <p class="muted small lt-intro">Yearly averages for this area. Open a card to see the change and how sure it is.</p>
    ${cards.join("")}`
}

// ------------------------------------------------------------------ insights (replaces "Not checked yet")

/** What a clear rise or fall means, in plain words. */
const MEANING = {
  sst: { up: "The sea here is warmer than it was twenty years ago.", down: "The sea here is cooler than it was twenty years ago." },
  air_temp: { up: "The air is warming along with the sea.", down: "The air is cooling." },
  rain: { up: "It rains more than it used to.", down: "It rains less than it used to." },
  salinity: { up: "The water is getting saltier.", down: "The water is getting slightly fresher." },
  ph: { up: "The water is becoming less acidic.", down: "The water is slowly becoming more acidic, as in oceans worldwide (ocean acidification)." },
  nitrate: { up: "There is more nitrate in the water (model estimate).", down: "There is less nitrate in the water (model estimate)." },
  phosphate: { up: "There is more phosphate in the water (model estimate).", down: "There is less phosphate in the water (model estimate)." },
}
const mean = (xs) => xs.reduce((a, b) => a + b, 0) / xs.length

/** Average of the first and last five complete years, e.g. {from:"2003–2007", a:28.7, to:"2020–2024", b:29.3}. */
export function firstLast(series, years, n = 5) {
  const pts = years.map((y, i) => [y, series.annual[i]]).filter(([, v]) => v != null)
  if (pts.length < 2 * n) return null
  const head = pts.slice(0, n)
  const tail = pts.slice(-n)
  // "2019–2024 without 2023" when an incomplete year sits inside the five.
  const label = (run) => {
    const y0 = run[0][0]
    const y1 = run[n - 1][0]
    const gaps = years.filter((y) => y > y0 && y < y1 && !run.some((p) => p[0] === y))
    return `${y0}–${y1}${gaps.length ? ` without ${gaps.join(", ")}` : ""}`
  }
  return { from: label(head), a: mean(head.map((p) => p[1])), to: label(tail), b: mean(tail.map((p) => p[1])) }
}

/** Clear changes as sentences, and the variables with no clear change. */
export function changeLines(region) {
  const clear = []
  const flat = []
  for (const k of ORDER) {
    const s = region.series[k]
    if (!s?.trend) continue
    if (!s.trend.significant) { flat.push(s.name.toLowerCase()); continue }
    const dir = s.trend.slope_per_decade > 0 ? "up" : "down"
    const amount = `${Math.abs(s.trend.change_over_period).toFixed(s.digits)}${s.unit ? ` ${s.unit}` : ""}`
    clear.push(`<b>${esc(s.name)} ${dir === "up" ? "rose" : "fell"} about ${esc(amount)}</b> (${esc(signed(s.trend.slope_per_decade, s.digits))}${s.unit ? ` ${esc(s.unit)}` : ""} per decade). ${esc(MEANING[k][dir])}`)
  }
  return { clear, flat }
}

/** The long-term values set against the species' range: the warmest and the freshest month. */
export function rangeLines(region, years, rules, species) {
  const out = []
  const sst = region.series.sst
  if (rules?.sst && sst) {
    const fl = firstLast(sst, years)
    const c = sst.climatology.map((v, i) => [v, i]).filter(([v]) => v != null)
    if (c.length === 12) {
      const [hot, m] = c.reduce((a, b) => (b[0] > a[0] ? b : a))
      const where = hot > rules.sst.max ? `above the ${rules.sst.max} °C upper limit` : `${(rules.sst.max - hot).toFixed(1)} °C below the ${rules.sst.max} °C upper limit`
      out.push(`${fl ? `Yearly sea temperature went from ${fl.a.toFixed(1)} °C (${fl.from}) to ${fl.b.toFixed(1)} °C (${fl.to}). ` : ""}The warmest month, ${MONTHS[m]}, averages ${hot.toFixed(1)} °C, ${where} of the range used for ${species}.`)
    }
  }
  const sal = region.series.salinity
  if (rules?.salinity && sal) {
    const c = sal.climatology.map((v, i) => [v, i]).filter(([v]) => v != null)
    if (c.length === 12) {
      const [low, m] = c.reduce((a, b) => (b[0] < a[0] ? b : a))
      const where = low < rules.salinity.min ? `below the ${rules.salinity.min} PSU lower limit` : `${(low - rules.salinity.min).toFixed(1)} PSU above the ${rules.salinity.min} PSU lower limit`
      out.push(`The freshest month, ${MONTHS[m]}, averages ${low.toFixed(1)} PSU, ${where}.`)
    }
  }
  return out
}

/**
 * "What the data tells us": what changed, what it means against the safe range, and which
 * data are behind the page and what they cannot show.
 * @param {{place:string, rules?:any, species?:string, ruleSources?:string[]}} opts
 */
export function insightsHtml(doc, regionId, { place, rules = null, species = null, ruleSources = [] } = {}) {
  const region = regionId ? doc?.regions?.[regionId] : null
  const y0 = doc?.years?.[0]
  const y1 = doc?.years?.[doc.years.length - 1]
  const blocks = []
  if (region) {
    const { clear, flat } = changeLines(region)
    blocks.push(`
      <h3>What changed in ${esc(place)}, ${y0}–${y1}</h3>
      <ul>${clear.map((l) => `<li>${l}</li>`).join("")}
        ${flat.length ? `<li>No clear change in ${esc(flat.join(", "))}. Their yearly values go up and down without a steady direction.</li>` : ""}</ul>`)
    const ranges = rules ? rangeLines(region, doc.years, rules, species) : []
    if (ranges.length) {
      blocks.push(`
      <h3>What it means for ${esc(species)}</h3>
      <ul>${ranges.map((l) => `<li>${esc(l)}</li>`).join("")}
        <li>A warmer or fresher sea is a stress on the seaweed, not a sign that it is sick.</li></ul>`)
    }
  }
  const sources = region ? [...new Set(ORDER.map((k) => region.series[k]?.source).filter(Boolean))] : []
  blocks.push(`
      <h3>Data behind this page</h3>
      <ul>
        <li><b>Last 90 days, daily:</b> NASA MUR sea temperature (about 1 km), Copernicus Marine salinity (about 9 km) and nitrate, phosphate and pH (about 25 km), with a 3-day Copernicus forecast.</li>
        ${sources.length ? `<li><b>${y0}–${y1}, monthly:</b> ${esc(sources.join("; "))}.</li>` : ""}
        <li><b>Area:</b> the sea within 5 km of the coast where ice-ice was reported, averaged over the area. Not measurements at a farm.</li>
        ${region ? `<li><b>Trend test:</b> Mann-Kendall on yearly averages, clear when p &lt; 0.05; size from Sen's slope with a 95% confidence interval.</li>` : ""}
        ${ruleSources.length ? `<li><b>Safe ranges:</b> ${esc(ruleSources.join("; "))}. Provisional.</li>` : ""}
      </ul>
      <h3>What these data cannot show</h3>
      <ul>
        <li>Whether the seaweed is sick or which pathogen is present. Water conditions are a warning, not a diagnosis.</li>
        <li>Nitrate, phosphate and pH have no validated safe range for these seaweeds, so they are shown but not rated.</li>
        <li>Sunlight reaching the seaweed needs water-clarity data, which is not connected yet.</li>
      </ul>`)
  return `
    <section class="insights-data">
      <h2 class="section-title">What the data tells us</h2>
      ${blocks.join("")}
    </section>`
}
