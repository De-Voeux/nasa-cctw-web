import { answer } from "./ask.js"
import { askAssistant, renderAnswer, MESSAGES } from "./assistant.js"

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c])

/**
 * "Ask SEAmon" chat (bottom left). Closed, it is only the input row; after the
 * first question it opens into a glass panel with the conversation.
 * Questions go to the assistant (POST /api/ask: verified sources and site data, with
 * citations). While it is not set up or cannot be reached, `answer()` in ask.js gives the
 * built-in local answers, which can carry "Show …" buttons that select a place on the globe.
 *
 * @param {HTMLElement} root
 * @param {{locations:any[], onShow:(loc:any)=>void, getContext?:()=>{species?:string, country?:string|null}}} opts
 *   getContext: the species and country selected in the panel, sent with the question
 */
export function mountChat(root, { locations, onShow, getContext = () => ({}) }) {
  const log = root.querySelector("#chat-log")
  const form = root.querySelector("#ask")
  const input = root.querySelector("#ask-input")
  const mic = root.querySelector("#mic")

  const setOpen = (open) => {
    root.dataset.open = String(open)
    root.classList.toggle("glass", open)
  }

  const push = (who, html) => {
    const el = document.createElement("div")
    el.className = `msg ${who}`
    el.innerHTML = html
    log.append(el)
    log.scrollTop = log.scrollHeight
    return el
  }

  let asking = false

  form.addEventListener("submit", async (e) => {
    e.preventDefault()
    const q = input.value.trim()
    if (!q) return input.focus()
    if (asking) return
    asking = true
    setOpen(true)
    push("user", esc(q))
    input.value = ""
    const bubble = push("bot", `<p class="thinking" aria-live="polite">Thinking…</p>`)
    try {
      const reply = await askAssistant(q, getContext())
      if (reply.ok) {
        bubble.innerHTML = renderAnswer(reply.data)
        return
      }
      if (reply.reason !== "unavailable") {
        bubble.innerHTML = MESSAGES[reply.reason]
        return
      }
      const res = answer(q, locations)
      const actions = (res.actions || [])
        .map((a) => `<button type="button" class="show-btn" data-goto="${a.loc.id}">${esc(a.label)}</button>`)
        .join("")
      // No note about why: when the assistant cannot be used the user just gets the built-in answer.
      bubble.innerHTML = res.html + (actions ? `<div class="msg-actions">${actions}</div>` : "")
      if (res.focus && res.autoShow) onShow(res.focus)
    } finally {
      asking = false
      log.scrollTop = log.scrollHeight
    }
  })

  log.addEventListener("click", (e) => {
    const b = e.target.closest("[data-goto]")
    if (!b) return
    e.preventDefault()
    const loc = locations.find((l) => l.id === b.dataset.goto)
    if (loc) onShow(loc)
  })

  root.querySelector("#chat-close").addEventListener("click", () => {
    log.innerHTML = ""
    setOpen(false)
    input.focus()
  })

  // Voice input through the browser's speech recognition, when it exists.
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition
  if (!SR) {
    mic.hidden = true
  } else {
    let rec = null
    mic.addEventListener("click", () => {
      if (rec) return rec.stop()
      rec = new SR()
      rec.lang = "en-US"
      rec.interimResults = true
      rec.onresult = (ev) => (input.value = [...ev.results].map((r) => r[0].transcript).join(""))
      rec.onend = () => {
        rec = null
        mic.setAttribute("aria-pressed", "false")
        input.focus()
      }
      rec.onerror = rec.onend
      mic.setAttribute("aria-pressed", "true")
      rec.start()
    })
  }

  setOpen(false)
}
