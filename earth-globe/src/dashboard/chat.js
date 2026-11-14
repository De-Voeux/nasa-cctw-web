const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c])

/**
 * The conversation that opens above the ask input: the user's questions on the
 * right, the answers on the left. Closing it keeps the history; asking again
 * reopens it.
 */
export class Chat {
  /**
   * @param {{bar:HTMLElement, panel:HTMLElement, log:HTMLElement, closeBtn:HTMLElement, onGoto:(id:string)=>void}} opts
   */
  constructor({ bar, panel, log, closeBtn, onGoto }) {
    this.bar = bar
    this.panel = panel
    this.log = log
    closeBtn.addEventListener("click", () => this.close())
    log.addEventListener("click", (e) => {
      const a = e.target.closest("[data-goto]")
      if (!a) return
      e.preventDefault()
      onGoto(a.dataset.goto)
    })
  }

  open() {
    this.panel.hidden = false
    this.bar.classList.add("has-chat")
  }

  close() {
    this.panel.hidden = true
    this.bar.classList.remove("has-chat")
  }

  /** A question typed by the user. Plain text, escaped here. */
  user(text) {
    this._add("user", `<p>${esc(text)}</p>`)
  }

  /** An answer. `html` must already be escaped (see ask.js). */
  bot(html) {
    this._add("bot", html)
  }

  /** A bubble that says the answer is on its way; call `.resolve(html)` when it arrives. */
  pending() {
    const msg = this._add("bot", `<p class="thinking" aria-live="polite">Thinking…</p>`)
    return {
      resolve: (html) => {
        msg.firstChild.innerHTML = html
        this.log.scrollTop = this.log.scrollHeight
      },
    }
  }

  _add(role, html) {
    const msg = document.createElement("div")
    msg.className = `msg ${role}`
    msg.innerHTML = `<div class="bubble">${html}</div>`
    this.log.append(msg)
    this.open()
    this.log.scrollTop = this.log.scrollHeight
    return msg
  }
}
