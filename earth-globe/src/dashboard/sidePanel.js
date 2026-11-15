import { chevronLeft } from "./icons.js"
import { LEVELS } from "../data/stress.js"
import { driversFor, NOT_ASSESSED, DUMMY_NOTE } from "../data/sampleDrivers.js"
import { trendChart } from "./trendChart.js"

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c])
const WORDS = ["None", "One", "Two", "Three", "Four"]
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
    this.range = 30 // days of history in the trend charts (set from the date bar)
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
    else if (this._detail) this._redrawDetail()
  }

  /** Days of history the trend charts cover (7, 30 or 90). */
  setRange(days) {
    this.range = days
    if (this.mode !== "list" && this._detail) this._redrawDetail()
  }

  /** Redraw the open place for a new day or range, keeping the scroll position. */
  _redrawDetail() {
    const top = this.body.scrollTop
    this.showLocation(this._detail.loc, this._detail.a)
    this.body.scrollTop = top
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
            <span class="rc-level lv-${a.level}">${lv.label}</span>
          </span>
          ${chevronRight}
        </button>`
      })
      .join("")

    this.body.innerHTML = `
      <div class="region-list">${cards || `<p class="empty">No region matches these filters. Try removing one.</p>`}</div>`
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
        <button class="back" data-back>${chevronLeft} All regions</button>
        <h1>${esc(loc.name)}</h1>
        <p class="sub">${esc(loc.country)}${loc.note ? ` · ${esc(loc.note)}` : ""}</p>
        ${this._stressHtml(loc, a)}
        <div class="card">
          <h2>Reported problem</h2>
          <span class="pill">${esc(loc.concern)}</span>
          <p class="muted small" style="margin:8px 0 0">A research paper mentions ice-ice disease in this area. We haven’t checked the paper yet. Water conditions alone can’t tell if seaweed has ice-ice.</p>
        </div>
        <div class="card">
          <h2>Seaweed mentioned here</h2>
          <ul>${loc.taxa.map((t) => `<li><i>${esc(t)}</i></li>`).join("")}</ul>
        </div>
        <div class="card">
          <h2>How reliable this is</h2>
          <dl>
            <div class="kv"><dt>Source checked</dt><dd>Not yet</dd></div>
            <div class="kv"><dt>Paper reference</dt><dd>Not added yet</dd></div>
            <div class="kv"><dt>Location detail</dt><dd>Province or region only</dd></div>
            <div class="kv"><dt>Pin on the map</dt><dd>Approximate</dd></div>
          </dl>
        </div>
      </div>`
    this.body.scrollTop = 0
  }

  /** Days between the date-bar selection and today (about −92 … +3). */
  _dayOffset() {
    if (!this.day) return 0
    const t = new Date()
    t.setHours(0, 0, 0, 0)
    return Math.round((this.day.date - t) / 86400000)
  }

  /**
   * Stress summary and the stressors behind it ("What drives this"), each driver
   * with a trend chart. Stressor values are DUMMY (data/sampleDrivers.js) until
   * the data pipeline feeds the dashboard.
   */
  _stressHtml(loc, a) {
    const lv = LEVELS[a.level]
    const offset = this._dayOffset()
    // Charts cover the chosen range, or longer when the chosen day is further back.
    const data = driversFor(loc.id, a.level, Math.max(this.range, 1 - offset))
    const sel = data ? data.todayIndex + offset : 0
    const drivers = data ? data.items.filter((d) => d.driver) : []
    const others = data ? data.items.filter((d) => !d.driver) : []
    const total = data ? WORDS[data.items.length].toLowerCase() : ""
    const summary = !data
      ? `Not enough data to check this area yet. This doesn’t mean conditions are good.`
      : `${drivers.length ? `${WORDS[drivers.length]} of ${total}` : `None of the ${total}`} water conditions ${drivers.length === 1 ? "is" : "are"} outside the safe range for this seaweed. This is a warning about the water, not a sign the seaweed is sick.`

    const card = (d) => `
      <article class="driver${d.driver ? " is-driver" : ""}">
        <header>
          <h3>${esc(d.name)}</h3>
          <p class="driver-value">${d.values[sel].toFixed(d.digits)}<span> ${esc(d.unit)}</span></p>
        </header>
        <p class="driver-head">${esc(d.headline)}</p>
        ${d.driver ? trendChart(d, data.dates, data.todayIndex, sel) : ""}
        <p class="driver-src">${esc(d.source)}</p>
      </article>`

    return `
        <section class="stress-sum tint-${a.level}">
          <div class="stress-top">
            <img class="level-icon" src="${lv.icon}" alt="" width="81" height="65" decoding="async">
            <div>
              <span class="stress-badge badge-${a.level}">${lv.label}</span>
              ${data ? `<p class="confidence">How sure we are: <b>${data.confidence}</b></p>` : ""}
            </div>
          </div>
          <p>${summary}</p>
        </section>
        ${data ? `
        <h2 class="section-title">What’s causing this</h2>
        ${drivers.length ? drivers.map(card).join("") : `<p class="muted small">Nothing is outside the safe range.</p>`}
        <h2 class="section-title">Normal right now</h2>
        ${others.map(card).join("")}` : ""}
        <section class="not-assessed">
          <h2 class="section-title">Not checked yet</h2>
          <ul>${(data ? NOT_ASSESSED : [{ name: "Ocean conditions", why: "Satellite data isn’t connected yet." }])
            .map((x) => `<li><b>${esc(x.name)}</b> · ${esc(x.why)}</li>`).join("")}</ul>
        </section>
        ${data ? `<p class="fineprint">${esc(DUMMY_NOTE)} The stress level is a sample too, and the safe ranges for each seaweed are still being checked.</p>` : ""}
        <h2 class="section-title">About this place</h2>`
  }
}
