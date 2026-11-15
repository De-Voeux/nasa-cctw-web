// Trend Detective: a guided flow over the long-term data (longTermTrends.json).
// 1. Pick a question (one Earth-science variable, with a plain definition).
// 2. Pick a place.
// 3. See the yearly series, the trend test and the same question in every other place.
// The statistics come precomputed from build_trends.py; this file only words and draws them.

import { longTermChart, verdict, seasonLine, signed } from "./longTermTrend.js"

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c])

/** The questions, one per variable, with a definition a non-scientist can follow. */
export const QUESTIONS = [
  {
    key: "sst",
    ask: "Is the sea getting warmer?",
    what: "Sea surface temperature",
    define: "How warm the top layer of the sea is, measured from space by NASA satellites. Farmed red seaweeds grow best in a narrow warm band; long stretches of hotter water are one of the conditions linked to ice-ice outbreaks.",
    mission: "NASA JPL MUR (MODIS, VIIRS, AMSR2 and other satellites, blended)",
  },
  {
    key: "air_temp",
    ask: "Is the air getting hotter?",
    what: "Air temperature at 2 m",
    define: "The temperature of the air just above the surface. It follows the sea closely over small islands and coasts, and warms the shallow water where seaweed is farmed.",
    mission: "NASA POWER (MERRA-2 model)",
  },
  {
    key: "rain",
    ask: "Is it raining more or less?",
    what: "Rainfall",
    define: "Average rain per day. Heavy rain freshens and cools coastal water for a while, which can stress seaweed that needs salty water.",
    mission: "NASA GPM IMERG (Global Precipitation Measurement satellites)",
  },
  {
    key: "salinity",
    ask: "Is the sea getting less salty?",
    what: "Salinity",
    define: "How much salt is dissolved in the water, in practical salinity units (about grams of salt per kilogram of seawater). Rain and river water lower it.",
    mission: "Copernicus Marine ocean model (GLORYS12 reanalysis)",
  },
  {
    key: "ph",
    ask: "Is the sea becoming more acidic?",
    what: "pH",
    define: "A scale of how acidic or basic the water is. Seawater is slightly basic (about 8.0). When the ocean absorbs carbon dioxide from the air, pH falls: this is ocean acidification.",
    mission: "Copernicus Marine biogeochemistry model",
  },
  {
    key: "nitrate",
    ask: "Are nutrients in the water changing? (nitrate)",
    what: "Nitrate",
    define: "A nutrient that seaweed and algae need to grow. Too little slows growth; too much can feed algal blooms.",
    mission: "Copernicus Marine biogeochemistry model",
  },
  {
    key: "phosphate",
    ask: "Are nutrients in the water changing? (phosphate)",
    what: "Phosphate",
    define: "The other main nutrient for seaweed and algae, often washed in from land by rivers and run-off.",
    mission: "Copernicus Marine biogeochemistry model",
  },
]

/** Ready-made investigations for the demo. Each is [question key, data region id]. */
export const EXAMPLES = [
  { label: "Warming sea in Tawi-Tawi", key: "sst", region: "PH-TAWI" },
  { label: "Acidifying sea, everywhere", key: "ph", region: "ID-SOUTH-SUL" },
  { label: "Rain: no clear signal", key: "rain", region: "PH-PANG" },
  { label: "Nutrients: up in one sea, down in another", key: "nitrate", region: "ID-N-JAVA-SEA" },
]

const question = (key) => QUESTIONS.find((q) => q.key === key)

/** One-sentence answer to the question for one place. */
export function conclusion(series, place) {
  const t = series.trend
  if (!t) return `There are not enough complete years for ${place} to test this.`
  const unit = series.unit ? ` ${series.unit}` : ""
  const total = Math.abs(t.change_over_period).toFixed(series.digits)
  const span = `${t.first_year} to ${t.last_year}`
  if (!t.significant) {
    return `No clear trend in ${place}. The yearly values go up and down, but from ${span} they do not move steadily in one direction (p = ${t.p.toFixed(2)}, above 0.05).`
  }
  const dir = t.slope_per_decade > 0 ? "risen" : "fallen"
  return `Yes, a clear trend in ${place}: ${series.name.toLowerCase()} has ${dir} by about ${total}${unit} from ${span}, ${signed(t.slope_per_decade, series.digits)}${unit} per decade. A change this steady would be very unlikely by chance (p ${t.p < 0.001 ? "< 0.001" : `= ${t.p.toFixed(3)}`}).`
}

/** Every place's trend for one variable, largest rise first. */
export function compareRows(doc, key, names) {
  return Object.entries(doc?.regions || {})
    .map(([id, r]) => ({ id, name: names[id] || id, s: r.series[key] }))
    .filter((x) => x.s?.trend)
    .sort((a, b) => b.s.trend.slope_per_decade - a.s.trend.slope_per_decade)
}

/** A bar per place: length = slope per decade, solid = significant, hollow = not. */
export function compareHtml(rows, currentId) {
  if (!rows.length) return ""
  const max = Math.max(...rows.map((r) => Math.abs(r.s.trend.slope_per_decade))) || 1
  const unit = rows[0].s.unit
  const up = rows.filter((r) => r.s.trend.significant && r.s.trend.slope_per_decade > 0).length
  const down = rows.filter((r) => r.s.trend.significant && r.s.trend.slope_per_decade < 0).length
  const flat = rows.length - up - down
  return `
    <p class="dt-summary">${up} of ${rows.length} places show a clear rise, ${down} a clear fall, and ${flat} no clear trend.</p>
    <ul class="dt-bars" aria-label="Trend per decade in every place">${rows
      .map((r) => {
        const t = r.s.trend
        const w = (Math.abs(t.slope_per_decade) / max) * 50
        const side = t.slope_per_decade >= 0 ? `left:50%` : `right:50%`
        return `<li class="${r.id === currentId ? "is-current" : ""}">
          <button type="button" class="dt-bar-row" data-region="${esc(r.id)}">
            <span class="dt-bar-name">${esc(r.name)}</span>
            <span class="dt-bar-track"><span class="dt-bar ${t.significant ? "sig" : "ns"} ${t.slope_per_decade >= 0 ? "pos" : "neg"}" style="${side};width:${w.toFixed(1)}%"></span></span>
            <span class="dt-bar-val">${signed(t.slope_per_decade, r.s.digits)}</span>
          </button></li>`
      })
      .join("")}</ul>
    <p class="dt-legend"><i class="sig"></i>clear trend (p &lt; 0.05) <i class="ns"></i>no clear trend · ${esc(unit || "units")} per decade · tap a place to see its answer</p>`
}

/**
 * Mount the flow into a <dialog>.
 * @param {HTMLDialogElement} dialog
 * @param {{doc:any, places:{id:string, dataRegionId:string, name:string, country:string}[], onOpenPlace:(id:string)=>void}} opts
 */
export function mountDetective(dialog, { doc, places, onOpenPlace }) {
  const names = Object.fromEntries(places.filter((p) => p.dataRegionId).map((p) => [p.dataRegionId, p.name]))
  const placeFor = (regionId) => places.find((p) => p.dataRegionId === regionId)
  const state = { key: null, region: null }
  const y0 = doc.years[0]
  const y1 = doc.years[doc.years.length - 1]

  const steps = () => `
    <ol class="dt-steps" aria-label="Steps">${["Question", "Place", "Answer"]
      .map((s, i) => {
        const at = state.region ? 2 : state.key ? 1 : 0
        return `<li class="${i === at ? "on" : i < at ? "done" : ""}">${i + 1}. ${s}</li>`
      })
      .join("")}</ol>`

  const pickQuestion = () => `
    <h3 class="dt-h">What do you want to find out?</h3>
    <ul class="dt-qs">${QUESTIONS.filter((q) => Object.values(doc.regions).some((r) => r.series[q.key]))
      .map((q) => `<li><button type="button" class="dt-q" data-key="${q.key}"><b>${esc(q.ask)}</b><span>${esc(q.what)}</span></button></li>`)
      .join("")}</ul>
    <h3 class="dt-h">Or start from an example</h3>
    <div class="dt-examples">${EXAMPLES.filter((e) => doc.regions[e.region]?.series[e.key])
      .map((e) => `<button type="button" class="dt-chip" data-key="${e.key}" data-region="${e.region}">${esc(e.label)}</button>`)
      .join("")}</div>`

  const pickPlace = () => {
    const q = question(state.key)
    const byCountry = {}
    for (const p of places) {
      if (p.dataRegionId && doc.regions[p.dataRegionId]?.series[state.key]) (byCountry[p.country] ||= []).push(p)
    }
    return `
      <p class="dt-q-now"><b>${esc(q.ask)}</b></p>
      <div class="dt-define"><b>${esc(q.what)}</b>: ${esc(q.define)}<br><span class="dt-src">Measured by: ${esc(q.mission)}</span></div>
      <h3 class="dt-h">Where?</h3>
      ${Object.entries(byCountry)
        .map(([c, ps]) => `<p class="dt-country">${esc(c)}</p><div class="dt-places">${ps
          .map((p) => `<button type="button" class="dt-chip" data-region="${p.dataRegionId}">${esc(p.name)}</button>`)
          .join("")}</div>`)
        .join("")}`
  }

  const answer = () => {
    const q = question(state.key)
    const s = doc.regions[state.region].series[state.key]
    const place = names[state.region] || state.region
    const v = verdict(s)
    const season = seasonLine(s)
    return `
      <p class="dt-q-now"><b>${esc(q.ask)}</b> · ${esc(place)}</p>
      <section class="dt-answer tone-${v.tone}">
        <span class="lt-badge lt-${v.tone}">${esc(v.label)}</span>
        <p>${esc(conclusion(s, place))}</p>
      </section>
      ${longTermChart(s, doc.years)}
      <dl class="dt-facts">
        <div><dt>How much</dt><dd>${esc(v.detail || "Not tested")}</dd></div>
        ${season ? `<div><dt>Every year</dt><dd>${esc(season)}</dd></div>` : ""}
        <div><dt>What this is</dt><dd>${esc(q.define)}</dd></div>
        <div><dt>How we tested it</dt><dd>One average per year (${y0}–${y1}, complete years only) so the seasons cancel out. The Mann-Kendall test asks whether the values move steadily one way; p below 0.05 counts as a clear trend. Sen's slope gives the size of the change, with a 95% confidence interval.</dd></div>
        <div><dt>Data</dt><dd>${esc(s.source)}${s.product_version ? ` · ${esc(s.product_version)}` : ""}. Values for the wider sea area, not a farm.</dd></div>
      </dl>
      <h3 class="dt-h">The same question in every place</h3>
      ${compareHtml(compareRows(doc, state.key, names), state.region)}
      <div class="dt-actions">
        ${placeFor(state.region) ? `<button type="button" class="dt-btn primary" data-open="${placeFor(state.region).id}">Open ${esc(place)} on the map</button>` : ""}
        <button type="button" class="dt-btn" data-restart>Ask another question</button>
      </div>`
  }

  const render = () => {
    const view = state.region ? answer() : state.key ? pickPlace() : pickQuestion()
    dialog.innerHTML = `
      <div class="dt-wrap">
        <header class="dt-head">
          <div>
            <h2>Trend Detective</h2>
            <p>Is the water around seaweed farms changing? Pick a question and a place, and test ${y1 - y0 + 1} years of NASA and Copernicus data.</p>
          </div>
          <button type="button" class="dt-close" data-close aria-label="Close">✕</button>
        </header>
        ${steps()}
        ${state.key ? `<button type="button" class="dt-back" data-back>‹ Back</button>` : ""}
        <div class="dt-body">${view}</div>
      </div>`
    dialog.querySelector(".dt-body")?.scrollTo?.(0, 0)
  }

  dialog.addEventListener("click", (e) => {
    if (e.target === dialog) return dialog.close() // click on the backdrop
    const b = e.target.closest("button")
    if (!b) return
    if (b.hasAttribute("data-close")) return dialog.close()
    if (b.hasAttribute("data-restart")) Object.assign(state, { key: null, region: null })
    else if (b.hasAttribute("data-back")) state.region ? (state.region = null) : (state.key = null)
    else if (b.dataset.open) {
      dialog.close()
      return onOpenPlace?.(b.dataset.open)
    } else {
      if (b.dataset.key) state.key = b.dataset.key
      if (b.dataset.region) state.region = b.dataset.region
    }
    render()
  })

  return {
    open(key = null, region = null) {
      Object.assign(state, { key, region })
      render()
      dialog.showModal()
    },
  }
}
