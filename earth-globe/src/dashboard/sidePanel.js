import { chevronLeft } from "./icons.js"
import { LEVELS } from "../data/stress.js"

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c])
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
            <span class="rc-level lv-${a.level}">${lv.label}</span>
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
        <div class="card stress-card">
          <h2>Environmental stress</h2>
          <div class="stress-row">
            <img class="level-icon" src="${lv.icon}" alt="" width="81" height="65" decoding="async">
            <div>
              <span class="rc-level lv-${a.level}">${lv.label}</span>
              <p class="muted small" style="margin:4px 0 0">${esc(a.condition)}${
                a.level === "insufficient" ? ". NASA, Copernicus and Open-Meteo layers are not connected to this dashboard yet." : ""
              }</p>
            </div>
          </div>
        </div>
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
}
