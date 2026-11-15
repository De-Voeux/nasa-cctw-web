const SHORT = new Intl.DateTimeFormat("en", { day: "numeric", month: "short" })

/** A "nice" tick step (1, 2, 2.5 or 5 × 10ⁿ) giving about `count` ticks over `span`. */
function niceStep(span, count) {
  const raw = span / Math.max(1, count)
  const mag = 10 ** Math.floor(Math.log10(raw))
  const n = raw / mag
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * mag
}

/** Decimals needed to print `step` without rounding it away. */
const decimalsFor = (step) => (String(+step.toFixed(10)).split(".")[1] || "").length

/**
 * Trend chart for a stressor card, with a y axis (value ticks, unit, grid lines) and an
 * x axis (date ticks). Shows the measured line, the dashed forecast, a shaded band for
 * the safe range (or the usual range in sample data), a "Today" line, and a dot on the
 * day picked in the date bar.
 *
 * The SVG stretches to the card width (preserveAspectRatio="none"); labels and the dot
 * are HTML so they never get stretched.
 *
 * @param {{name:string, unit:string, digits:number, values:number[],
 *          baseline?:[number,number]|null, bandLabel?:string}} item
 *   baseline: the band to shade; bandLabel: its name in the legend ("Safe range" by default)
 * @param {Date[]} dates
 * @param {number} todayIndex  last measured point; later points are forecast
 * @param {number} selIndex    the day picked in the date bar
 */
export function trendChart(item, dates, todayIndex, selIndex) {
  const { values, baseline, digits, unit } = item
  const bandLabel = item.bandLabel || "Safe range"
  const n = values.length
  const hasBand = Array.isArray(baseline) && baseline.length === 2

  // y domain: the data and the band, widened to whole ticks.
  let lo = Math.min(...values, ...(hasBand ? [baseline[0]] : []))
  let hi = Math.max(...values, ...(hasBand ? [baseline[1]] : []))
  // A nearly flat series (pH) would otherwise get ticks finer than the values are printed.
  const minSpan = 4 * 10 ** -digits
  if (hi - lo < minSpan) {
    const mid = (hi + lo) / 2
    lo = mid - minSpan / 2
    hi = mid + minSpan / 2
  }
  const step = niceStep(hi - lo, 3)
  lo = Math.floor(lo / step) * step
  hi = Math.ceil(hi / step) * step
  if (lo < 0 && Math.min(...values) >= 0) lo = 0
  const yTicks = []
  for (let v = lo; v <= hi + step / 2; v += step) yTicks.push(+v.toFixed(10))
  const tickDigits = Math.min(4, decimalsFor(step))

  const H = 40
  const X = (i) => (n > 1 ? (i / (n - 1)) * 100 : 50)
  const Y = (v) => H - ((v - lo) / (hi - lo)) * H
  const pct = (v) => ((Y(v) / H) * 100).toFixed(2)
  const pts = (a, b) => values.slice(a, b + 1).map((v, k) => `${X(a + k).toFixed(2)},${Y(v).toFixed(2)}`).join(" ")
  const tx = X(todayIndex)
  const sel = Math.min(n - 1, Math.max(0, selIndex))
  const hasForecast = todayIndex < n - 1

  // x ticks: about four dates, always the first and the last.
  const xIdx = [...new Set([0, Math.round((n - 1) / 3), Math.round((2 * (n - 1)) / 3), n - 1])].filter((i) => i >= 0 && i < n)

  const f = (v) => v.toFixed(digits)
  const label = `${item.name}, ${SHORT.format(dates[0])} to ${SHORT.format(dates[n - 1])}: ${f(values[0])} to ${f(values[todayIndex])} ${unit}${hasForecast ? `, forecast ${f(values[n - 1])} ${unit}` : ""}. ${hasBand ? `${bandLabel} ${f(baseline[0])}–${f(baseline[1])} ${unit}.` : "No safe range set."}`

  return `
  <figure class="trend" role="img" aria-label="${label}">
    <span class="trend-unit" aria-hidden="true">${unit}</span>
    <div class="trend-y" aria-hidden="true">${yTicks
      .map((v) => `<span style="top:${pct(v)}%">${v.toFixed(tickDigits)}</span>`)
      .join("")}</div>
    <div class="trend-plot" aria-hidden="true">
      <svg viewBox="0 0 100 ${H}" preserveAspectRatio="none">
        ${yTicks.map((v) => `<line class="t-grid" x1="0" x2="100" y1="${Y(v).toFixed(2)}" y2="${Y(v).toFixed(2)}"/>`).join("")}
        ${hasForecast ? `<rect class="t-forecast-bg" x="${tx}" y="0" width="${100 - tx}" height="${H}"/>` : ""}
        ${hasBand ? `<rect class="t-band" x="0" y="${Y(baseline[1])}" width="100" height="${Y(baseline[0]) - Y(baseline[1])}"/>
        <line class="t-band-edge" x1="0" x2="100" y1="${Y(baseline[1])}" y2="${Y(baseline[1])}"/>
        <line class="t-band-edge" x1="0" x2="100" y1="${Y(baseline[0])}" y2="${Y(baseline[0])}"/>` : ""}
        <polyline class="t-obs" points="${pts(0, todayIndex)}"/>
        ${hasForecast ? `<polyline class="t-fc" points="${pts(todayIndex, n - 1)}"/>` : ""}
        <line class="t-today" x1="${tx}" x2="${tx}" y1="0" y2="${H}"/>
      </svg>
      <span class="t-x-today" style="left:${tx}%">Today</span>
      <span class="t-dot${sel > todayIndex ? " fc" : ""}" style="left:${X(sel)}%;top:${pct(values[sel])}%"></span>
    </div>
    <div class="trend-x" aria-hidden="true">${xIdx
      .map((i, k) => `<span class="${k === 0 ? "first" : i === n - 1 ? "last" : ""}" style="left:${X(i)}%">${SHORT.format(dates[i])}</span>`)
      .join("")}</div>
    <figcaption class="trend-legend">
      ${hasBand ? `<span><i class="k-band"></i>${bandLabel} ${f(baseline[0])}–${f(baseline[1])} ${unit}</span>` : ""}
      <span><i class="k-obs"></i>Measured</span>
      ${hasForecast ? `<span><i class="k-fc"></i>Forecast</span>` : ""}
      <span class="t-sel">● ${SHORT.format(dates[sel])}</span>
    </figcaption>
  </figure>`
}
