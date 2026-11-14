const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c])

const chevronDown = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>`

let openMenu = null // only one menu is open at a time

/**
 * A chip that opens a checkbox list with Cancel / Apply Filter. Ticks are staged
 * inside the menu and only take effect on Apply. Cancel, Escape or a tap outside
 * throw the staged ticks away.
 */
export class FilterMenu {
  /**
   * @param {HTMLElement} root  empty element the chip and its menu are drawn into
   * @param {{label:string, onApply:(selected:Set<string>)=>void}} opts
   */
  constructor(root, { label, onApply }) {
    this.root = root
    this.label = label
    this.onApply = onApply
    this.options = []
    this.applied = new Set()
    this.staged = new Set()
    this.isOpen = false
    this.uid = `fm-${Math.random().toString(36).slice(2, 8)}`

    root.classList.add("chip-wrap")
    root.innerHTML = `
      <button type="button" class="chip" aria-haspopup="true" aria-expanded="false" aria-controls="${this.uid}">
        <span class="chip-label"></span><span class="chip-n" hidden></span>${chevronDown}
      </button>
      <div class="menu" id="${this.uid}" role="group" aria-label="${esc(label)}" hidden>
        <div class="menu-list"></div>
        <div class="menu-actions">
          <button type="button" class="btn-cancel">Cancel</button>
          <button type="button" class="btn-apply">Apply Filter</button>
        </div>
      </div>`
    this.btn = root.querySelector(".chip")
    this.menu = root.querySelector(".menu")
    this.list = root.querySelector(".menu-list")
    this.nBadge = root.querySelector(".chip-n")
    root.querySelector(".chip-label").textContent = label

    this.btn.addEventListener("click", () => (this.isOpen ? this.close() : this.open()))
    root.querySelector(".btn-cancel").addEventListener("click", () => this.close(true))
    root.querySelector(".btn-apply").addEventListener("click", () => this.apply())
    this.list.addEventListener("change", (e) => {
      const cb = e.target
      if (!(cb instanceof HTMLInputElement)) return
      if (cb.checked) this.staged.add(cb.value)
      else this.staged.delete(cb.value)
    })
    this.menu.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        e.stopPropagation()
        this.close(true)
      }
    })
  }

  /**
   * Replace the options. `selected` is the applied selection; values that are no
   * longer offered are dropped from it.
   * @param {{value:string,label:string}[]} options
   * @param {Set<string>} selected
   */
  setOptions(options, selected) {
    this.options = options
    const offered = new Set(options.map((o) => o.value))
    this.applied = new Set([...selected].filter((v) => offered.has(v)))
    this.staged = new Set(this.applied)
    this._renderList()
    this._renderBadge()
    return this.applied
  }

  _renderList() {
    this.list.innerHTML = this.options
      .map(
        (o) => `
        <label class="opt">
          <input type="checkbox" value="${esc(o.value)}"${this.staged.has(o.value) ? " checked" : ""}>
          <span class="box" aria-hidden="true"></span>
          <span class="opt-label">${esc(o.label)}</span>
        </label>`,
      )
      .join("")
  }

  _renderBadge() {
    const n = this.applied.size
    const filtered = this.options.length > 0 && n !== this.options.length
    this.nBadge.hidden = !filtered
    this.nBadge.textContent = filtered ? `${n}/${this.options.length}` : ""
    this.btn.classList.toggle("is-filtered", filtered)
  }

  open() {
    if (openMenu && openMenu !== this) openMenu.close(true)
    this.staged = new Set(this.applied)
    this._renderList()
    this.isOpen = true
    openMenu = this
    this.menu.hidden = false
    this.menu.scrollIntoView({ block: "nearest" }) // inside a scrolling sheet it may open below the fold
    this.btn.setAttribute("aria-expanded", "true")
    this.list.querySelector("input")?.focus()
  }

  /** @param {boolean} [discard] drop the staged ticks (the default for every way out but Apply) */
  close(discard = true) {
    if (!this.isOpen) return
    if (discard) this.staged = new Set(this.applied)
    this.isOpen = false
    if (openMenu === this) openMenu = null
    this.menu.hidden = true
    this.btn.setAttribute("aria-expanded", "false")
  }

  apply() {
    this.applied = new Set(this.staged)
    this._renderBadge()
    this.close(false)
    this.onApply(new Set(this.applied))
    this.btn.focus()
  }
}

// A tap outside the open menu, or Escape, closes it without applying.
document.addEventListener("pointerdown", (e) => {
  if (openMenu && !openMenu.root.contains(e.target)) openMenu.close(true)
})
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && openMenu) {
    const m = openMenu
    m.close(true)
    m.btn.focus()
  }
})
