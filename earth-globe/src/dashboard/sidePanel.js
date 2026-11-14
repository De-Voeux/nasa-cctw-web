import { waveIcon, chevronLeft } from "./icons.js"
import { SOURCE } from "../data/reportedLocations.js"

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c])
const DAY = new Intl.DateTimeFormat("en", { weekday: "short", day: "numeric", month: "short" })
const KIND = { history: "History · observed", now: "Today · analysis", forecast: "Forecast · model" }

/**
 * Right-hand panel: location list (default), location detail, or an ask-bar answer.
 */
export class SidePanel {
  /**
   * @param {HTMLElement} body
   * @param {{locations:any[], onSelect:(loc:any)=>void, onBack:()=>void}} opts
   */
  constructor(body, { locations, onSelect, onBack }) {
    this.body = body
    this.locations = locations
    this.onSelect = onSelect
    this.onBack = onBack
    this.filter = ""
    this.day = null
    this.selectedId = null
    this.answer = null

    body.addEventListener("click", (e) => {
      const row = e.target.closest("[data-loc]")
      if (row) {
        const loc = this.locations.find((l) => l.id === row.dataset.loc)
        if (loc) this.onSelect(loc)
        return
      }
      if (e.target.closest("[data-back]")) this.onBack()
    })
  }

  setFilter(q) {
    this.filter = q.trim().toLowerCase()
    this.answer = null
    this.showList()
  }

  setDay(day) {
    this.day = day
    if (this.mode === "list") this.showList()
    if (this.mode === "detail") this.showLocation(this.locations.find((l) => l.id === this.selectedId))
  }

  _dateStatus() {
    if (!this.day) return ""
    return `<p class="date-status">${DAY.format(this.day.date)} · ${KIND[this.day.kind]} — environmental layers not ingested yet</p>`
  }

  showList() {
    this.mode = "list"
    this.selectedId = null
    const q = this.filter
    const match = (l) => !q || `${l.name} ${l.country} ${l.note || ""} ${l.taxa.join(" ")}`.toLowerCase().includes(q)
    const rows = this.locations.filter(match)
    const byCountry = Map.groupBy
      ? Map.groupBy(rows, (l) => l.country)
      : rows.reduce((m, l) => m.set(l.country, [...(m.get(l.country) || []), l]), new Map())

    const groups = [...byCountry.entries()]
      .sort((a, b) => b[1].length - a[1].length)
      .map(
        ([country, locs]) => `
        <h2 class="group-title">${esc(country)} · ${locs.length}</h2>
        ${locs
          .map(
            (l) => `
          <button class="loc-row" data-loc="${l.id}">
            <span class="loc-icon">${waveIcon}</span>
            <span><span class="name">${esc(l.name)}</span><br>
            <span class="meta">${l.taxa.length} ${l.taxa.length === 1 ? "taxon" : "taxa"} · ${esc(l.concern)} · unverified</span></span>
          </button>`,
          )
          .join("")}`,
      )
      .join("")

    this.body.innerHTML = `
      <div class="panel-head">
        <p class="eyebrow">Southeast Asia</p>
        <h1>Reported ice-ice locations</h1>
        <p class="muted small">${rows.length} of ${this.locations.length} places named in candidate research leads.</p>
      </div>
      ${this._dateStatus()}
      ${this.answer || ""}
      <p class="notice">These are unverified mentions from <b>${esc(SOURCE.label)}</b>, not confirmed cases, farm locations, or outbreak counts.</p>
      ${groups || `<p class="empty">No place matches “${esc(q)}”.</p>`}`
  }

  showLocation(loc) {
    if (!loc) return this.showList()
    this.mode = "detail"
    this.selectedId = loc.id
    this.body.innerHTML = `
      <div class="detail">
        <button class="back" data-back>${chevronLeft} All locations</button>
        <h1>${esc(loc.name)}</h1>
        <p class="sub">${esc(loc.country)}${loc.note ? ` · ${esc(loc.note)}` : ""}</p>
        ${this._dateStatus()}
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
        <div class="card">
          <h2>Environmental stress</h2>
          <p class="muted small" style="margin:0">Insufficient data — NASA, Copernicus and Open-Meteo layers are not connected to this dashboard yet.</p>
        </div>
      </div>`
    this.body.scrollTop = 0
  }

  /** Show an ask-bar answer above the list. `html` must already be escaped. */
  showAnswer(question, html) {
    this.answer = `<div class="answer"><p class="q">“${esc(question)}”</p>${html}</div>`
    this.filter = ""
    this.showList()
    this.body.scrollTop = 0
  }
}
