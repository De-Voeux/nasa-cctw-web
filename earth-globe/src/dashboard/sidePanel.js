import { chevronLeft } from "./icons.js"
import { LEVELS } from "../data/stress.js"
import { driversFor, NOT_ASSESSED, DUMMY_NOTE } from "../data/sampleDrivers.js"
import { trendChart } from "./trendChart.js"

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c])
const WORDS = ["None", "One", "Two", "Three", "Four"]
const countLabel = (count) => WORDS[count] || String(count)
export const statusLabel = (assessment) => assessment?.scored
  ? (LEVELS[assessment.level]?.label || "Insufficient Data")
  : assessment?.observed ? "Observed — Risk Not Assessed" : (LEVELS[assessment?.level]?.label || "Insufficient Data")
const chevronRight = `<svg class="rc-go" viewBox="0 0 24 24" aria-hidden="true"><path d="m9 6 6 6-6 6"/></svg>`

/**
 * Right-hand panel body: the region cards (default) or one region's detail.
 * Filtering, sorting and the assessment of each region happen in main.js; this
 * only draws what it is given.
 */
export class SidePanel {
  /**
   * @param {HTMLElement} body
   * @param {{root:HTMLElement, onSelect:(id:string)=>void, onBack:()=>void}} opts
   *   root: the panel element, which gets data-mode="list"|"detail" for CSS
   */
  constructor(body, { root, onSelect, onBack }) {
    this.body = body
    this.root = root
    this.onSelect = onSelect
    this.onBack = onBack
    this.day = null
    this.selectedId = null
    this.mode = "list"
    this.lastRows = []

    body.addEventListener("click", (e) => {
      const card = e.target.closest("[data-loc]")
      if (card) return this.onSelect(card.dataset.loc)
      if (e.target.closest("[data-back]")) this.onBack()
    })
  }

  setDay(day) {
    this.day = day
    if (this.mode === "list") this.showList(this.lastRows)
    else if (this._detail) this.showLocation(this._detail.loc, this._detail.a)
  }

  _setMode(mode) {
    this.mode = mode
    this.root.dataset.mode = mode
  }

  /**
   * @param {{loc:any, a:{level:string, condition:string}}[]} rows  already filtered and sorted
   */
  showList(rows) {
    this.lastRows = rows
    this._setMode("list")
    this.selectedId = null
    const cards = rows
      .map(({ loc, a }) => {
        const lv = LEVELS[a.level]
        return `
        <button class="region-card" type="button" data-loc="${loc.id}">
          <img class="level-icon" src="${lv.icon}" alt="" width="81" height="65" decoding="async">
          <span class="rc-text">
            <span class="rc-name">${esc(loc.name)}</span>
            <span class="rc-sub">${esc(loc.country)}</span>
            <span class="rc-cond">${esc(a.condition)}</span>
            <span class="rc-level lv-${a.level}${a.observed ? " observed" : ""}">${statusLabel(a)}</span>
          </span>
          ${chevronRight}
        </button>`
      })
      .join("")

    this.body.innerHTML = `
      <div class="region-list">${cards || `<p class="empty">No place matches the filters.</p>`}</div>`
  }

  /** @param {any} loc @param {{level:string, condition:string}} a */
  showLocation(loc, a) {
    if (!loc) return this.showList(this.lastRows)
    this._setMode("detail")
    this.selectedId = loc.id
    this._detail = { loc, a }
    const lv = LEVELS[a.level]
    this.body.innerHTML = `
      <div class="detail">
        <button class="back" data-back>${chevronLeft} All locations</button>
        <h1>${esc(loc.name)}</h1>
        <p class="sub">${esc(loc.country)}${loc.note ? ` · ${esc(loc.note)}` : ""}</p>
        ${this._stressHtml(loc, a)}
        <div class="card">
          <h2>Reported concern</h2>
          <span class="pill">${esc(loc.concern)}</span>
          <p class="muted small" style="margin:8px 0 0">Said to be mentioned in a paper for this area. Environmental indicators cannot diagnose ice-ice.</p>
        </div>
        <div class="card">
          <h2>Host taxa as supplied</h2>
          <ul>${loc.taxa.map((t) => `<li><i>${esc(t)}</i></li>`).join("")}</ul>
        </div>
        <div class="card">
          <h2>Evidence</h2>
          <dl>
            <div class="kv"><dt>Verification</dt><dd>Pending</dd></div>
            <div class="kv"><dt>Citation</dt><dd>Not yet attached</dd></div>
            <div class="kv"><dt>Spatial precision</dt><dd>Province / region</dd></div>
            <div class="kv"><dt>Marker position</dt><dd>Approximate</dd></div>
          </dl>
        </div>
      </div>`
    this.body.scrollTop = 0
  }

  /** Select the closest available value without extending observations into the future. */
  _selectedIndex(data) {
    if (!this.day || !data?.dates?.length) return data?.todayIndex || 0
    const target = this.day.date.getTime()
    let best = 0
    let distance = Infinity
    data.dates.forEach((date, i) => {
      const d = Math.abs(date.getTime() - target)
      if (d < distance) { best = i; distance = d }
    })
    return best
  }

  /**
   * Stress summary and the environmental series behind it. Demo series remain
   * available only when the explicit demo query parameter is used.
   */
  _stressHtml(loc, a) {
    const lv = LEVELS[a.level]
    const data = a.data || (a.demo ? driversFor(loc.id, a.level) : null)
    const sel = data ? this._selectedIndex(data) : 0
    const drivers = data ? data.items.filter((d) => d.driver) : []
    const others = data ? data.items.filter((d) => !d.driver) : []
    // Live observations can contain more indicators than the demo copy was
    // written for. Keep detail rendering total for any item count.
    const total = data ? countLabel(data.items.length).toLowerCase() : ""
    const summary = a.observed
      ? `${esc(a.condition)}. ${a.scored ? "This is a provisional environmental screening signal, not a disease diagnosis." : "These are environmental observations; no biological stress level has been assigned."}`
      : !data
      ? `${esc(a.condition)}. There isn't enough data to assess this region, which is not the same as low stress.`
      : `${drivers.length ? `${countLabel(drivers.length)} of ${total}` : `None of the ${total}`} evaluated stressors ${drivers.length === 1 ? "is" : "are"} outside the species reference range. This is an environmental warning, not a disease diagnosis.`

    const card = (d) => {
      const index = Math.min(d.values.length - 1, d.dates ? this._selectedIndex({ dates: d.dates, todayIndex: d.values.length - 1 }) : sel)
      const chartToday = Math.min(d.values.length - 1, d.todayIndex ?? d.values.length - 1)
      return `
      <article class="driver${d.driver ? " is-driver" : ""}">
        <header>
          <h3>${esc(d.name)}</h3>
          <p class="driver-value">${d.values[index].toFixed(d.digits)}<span> ${esc(d.unit)}</span></p>
        </header>
        <p class="driver-head">${esc(d.headline || "Observed environmental value")}</p>
        ${a.observed || d.driver ? trendChart(d, d.dates || data.dates, chartToday, index) : ""}
        <p class="driver-src">${esc(d.source)}${d.product_version ? ` · product ${esc(d.product_version)}` : ""}<br>Species reference range: not yet reviewed</p>
      </article>`
    }

    return `
        <section class="stress-sum tint-${a.level}">
          <div class="stress-top">
            <img class="level-icon" src="${lv.icon}" alt="" width="81" height="65" decoding="async">
            <div>
              <span class="stress-badge badge-${a.level}">${statusLabel(a)}</span>
              ${data ? `<p class="confidence">Evidence confidence: <b>${data.confidence}</b></p>` : ""}
            </div>
          </div>
          <p>${summary}</p>
        </section>
        ${data ? `
        <h2 class="section-title">What drives this</h2>
        ${drivers.length ? drivers.map(card).join("") : `<p class="muted small">${a.scored ? "All active indicators are within provisional reference ranges." : "No stressor classification is active. The cards below show observed values only."}</p>`}
        <h2 class="section-title">Also checked</h2>
        ${others.map(card).join("")}` : ""}
        <section class="not-assessed">
          <h2 class="section-title">Not assessed</h2>
          <ul>${(data?.notAssessed || (data ? NOT_ASSESSED : [{ name: "All stressors", why: "Environmental layers are not connected yet." }]))
            .map((x) => `<li><b>${esc(x.name)}</b> · ${esc(x.why)}</li>`).join("")}</ul>
        </section>
        ${a.demo ? `<p class="fineprint">${esc(DUMMY_NOTE)} Stress level is a demo value.</p>` : ""}
        <h2 class="section-title">About this place</h2>`
  }
}
