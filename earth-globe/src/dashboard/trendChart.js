const SHORT = new Intl.DateTimeFormat("en", { day: "numeric", month: "short" })

/**
 * Small trend chart for a stressor card: observed line, dashed forecast,
 * baseline band, a "Today" line, and a dot on the selected day.
 * Values are labelled on the y axis and dates on the x axis, and the legend
 * sits under the plot so no label is drawn over the line.
 *
 * The SVG stretches to the card width (preserveAspectRatio="none"); labels and
 * the dot are HTML so they never get stretched.
 *
 * @param {{name:string, unit:string, digits:number, baseline:[number,number], values:number[]}} item
 * @param {Date[]} dates
 * @param {number} todayIndex
 * @param {number} selIndex  the day picked in the date bar
 */
export function trendChart(item, dates, todayIndex, selIndex) {
  const { values, baseline, digits, unit } = item
  const n = values.length
  const hasBaseline = Array.isArray(baseline) && baseline.length === 2
  let lo = Math.min(...values, ...(hasBaseline ? [baseline[0]] : []))
  let hi = Math.max(...values, ...(hasBaseline ? [baseline[1]] : []))
  const pad = (hi - lo) * 0.12 || 1
  lo -= pad
  hi += pad
  if (lo < 0 && Math.min(...values) >= 0) lo = 0

  const X = (i) => (i / (n - 1)) * 100
  const Y = (v) => 40 - ((v - lo) / (hi - lo)) * 40
  const pts = (a, b) => values.slice(a, b + 1).map((v, k) => `${X(a + k).toFixed(2)},${Y(v).toFixed(2)}`).join(" ")
  const tx = X(todayIndex)
  const sel = Math.min(n - 1, Math.max(0, selIndex))

  const f = (v) => v.toFixed(digits)
  const label = `${item.name}, ${SHORT.format(dates[0])} to ${SHORT.format(dates[n - 1])}: ${f(values[0])} to ${f(values[todayIndex])} ${unit}. ${hasBaseline ? `Baseline ${f(baseline[0])}–${f(baseline[1])} ${unit}.` : "Observed values only."}`

  return `
  <figure class="trend" role="img" aria-label="${label}">
    <div class="trend-y" aria-hidden="true"><span>${f(hi)}</span><span>${f(lo)}</span></div>
    <div class="trend-plot" aria-hidden="true">
      <svg viewBox="0 0 100 40" preserveAspectRatio="none">
        ${todayIndex < n - 1 ? `<rect class="t-forecast-bg" x="${tx}" y="0" width="${100 - tx}" height="40"/>` : ""}
        ${hasBaseline ? `<rect class="t-band" x="0" y="${Y(baseline[1])}" width="100" height="${Y(baseline[0]) - Y(baseline[1])}"/>` : ""}
        <polyline class="t-obs" points="${pts(0, todayIndex)}"/>
        ${todayIndex < n - 1 ? `<polyline class="t-fc" points="${pts(todayIndex, n - 1)}"/>` : ""}
        <line class="t-today" x1="${tx}" x2="${tx}" y1="0" y2="40"/>
      </svg>
      <span class="t-x-today" style="left:${tx}%">Today</span>
      <span class="t-dot${sel > todayIndex ? " fc" : ""}" style="left:${X(sel)}%;top:${(Y(values[sel]) / 40) * 100}%"></span>
    </div>
    <div class="trend-x" aria-hidden="true">
      <span>${SHORT.format(dates[0])}</span>
      <span>${SHORT.format(dates[n - 1])}</span>
    </div>
    <figcaption class="trend-legend">
      ${hasBaseline ? `<span><i class="k-band"></i>Baseline</span>` : ""}
      <span><i class="k-obs"></i>Observed</span>
      ${todayIndex < n - 1 ? `<span><i class="k-fc"></i>Forecast</span>` : ""}
      <span class="t-sel">● ${SHORT.format(dates[sel])}</span>
    </figcaption>
  </figure>`
}
