/**
 * Client for POST /api/ask (worker/ask.js). Turns the structured answer into the HTML of
 * a chat bubble. Every string from the server is escaped here: the answer is model text,
 * so it is never inserted as HTML, and only https links are made clickable.
 */
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c])
const safeHref = (u) => (typeof u === "string" && /^https:\/\//i.test(u) ? u : null)
const href = (s) => safeHref(s.url) || (s.doi ? `https://doi.org/${encodeURI(s.doi)}` : null)

/**
 * @returns {Promise<{ok:true, data:object} | {ok:false, reason:"unavailable"|"limited"|"error"}>}
 *   "unavailable" means the assistant is not set up, out of quota or unreachable: the caller falls
 *   back to the built-in answers, and `why` ("quota" | "down" | undefined) says which (not shown to the user). "limited" is a rate limit: say so instead of falling back.
 */
export async function askAssistant(question, { species, country, history } = {}, fetchImpl = fetch) {
  let res
  try {
    res = await fetchImpl("/api/ask", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ question, species, country, history }),
    })
  } catch {
    return { ok: false, reason: "unavailable" }
  }
  if (res.status === 429) return { ok: false, reason: "limited" }
  if (res.status === 400) return { ok: false, reason: "invalid" }
  if (res.status === 503 || res.status === 404 || res.status === 405) {
    // 503 may say why: "quota" (daily limit spent) or "down" (providers unreachable).
    let why
    try {
      why = (await res.json())?.reason
    } catch {}
    return { ok: false, reason: "unavailable", why }
  }
  if (!res.ok) return { ok: false, reason: "error" }
  try {
    return { ok: true, data: await res.json() }
  } catch {
    return { ok: false, reason: "error" }
  }
}

/**
 * A small, safe subset of Markdown for model answers: paragraphs, line breaks, `-`/`*`/`•`
 * and `1.` lists, `#` headings (shown as bold), **bold** and `code`. Everything is escaped
 * FIRST and the markers are turned into tags afterwards, so no text from the server can
 * become markup, and there are no links or images. Anything else (tables, nested lists,
 * HTML) stays as plain text.
 */
export function renderMarkdown(text) {
  const inline = (line) =>
    esc(line)
      .replace(/`([^`\n]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*\n]+?)\*\*/g, "<strong>$1</strong>")
      // *italic*, as models write species names: a single star that touches text on both sides and is not part of a word
      .replace(/(^|[^*\w])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![*\w])/g, "$1<em>$2</em>")
  const out = []
  let para = []
  let list = null // { tag: "ul" | "ol", items: [] }
  const flushPara = () => {
    if (para.length) out.push(`<p>${para.map(inline).join("<br>")}</p>`)
    para = []
  }
  const flushList = () => {
    if (list) out.push(`<${list.tag}>${list.items.map((i) => `<li>${inline(i)}</li>`).join("")}</${list.tag}>`)
    list = null
  }
  for (const raw of String(text).split(/\r?\n/)) {
    const line = raw.trimEnd()
    let m
    if (!line.trim()) {
      flushPara()
      flushList()
    } else if ((m = /^\s*[-*•]\s+(.*)$/.exec(line))) {
      flushPara()
      if (list?.tag !== "ul") (flushList(), (list = { tag: "ul", items: [] }))
      list.items.push(m[1])
    } else if ((m = /^\s*\d{1,2}[.)]\s+(.*)$/.exec(line))) {
      flushPara()
      if (list?.tag !== "ol") (flushList(), (list = { tag: "ol", items: [] }))
      list.items.push(m[1])
    } else if ((m = /^#{1,4}\s+(.*)$/.exec(line))) {
      flushPara()
      flushList()
      out.push(`<p><strong>${inline(m[1])}</strong></p>`)
    } else {
      flushList()
      para.push(line.trim())
    }
  }
  flushPara()
  flushList()
  return out.join("")
}

const paragraphs = renderMarkdown

/** Bubble HTML for an answer from the server. */
export function renderAnswer(a) {
  const parts = [paragraphs(a.answer_md)]
  if (a.claims?.length) {
    parts.push(
      `<ul class="claims">${a.claims
        .map((c) => `<li>${esc(c.text)} ${c.source_ns.map((n) => `<sup class="cite">[${n}]</sup>`).join("")}</li>`)
        .join("")}</ul>`,
    )
  }
  if (a.data_used?.length) {
    parts.push(
      `<p class="data-used">Data: ${a.data_used
        .map((d) => esc([d.site_id, d.variable, d.from && d.to ? `${d.from} to ${d.to}` : "", ...(d.products ?? [])].filter(Boolean).join(" · ")))
        .join("; ")}</p>`,
    )
  }
  if (a.sources?.length) {
    parts.push(
      `<ol class="sources">${a.sources
        .map((s) => {
          const h = href(s)
          return `<li>${h ? `<a class="link" href="${esc(h)}" target="_blank" rel="noopener noreferrer">${esc(s.citation)}</a>` : esc(s.citation)}</li>`
        })
        .join("")}</ol>`,
    )
  }
  if (a.abstained) parts.push(`<p class="muted small">Not enough evidence in the sources we have.</p>`)
  return parts.join("")
}

/** Longest question the server accepts (worker/ask.js MAX_QUESTION). */
export const MAX_QUESTION = 500

export const MESSAGES = {
  limited: `<p>That is a lot of questions in a short time. Please wait a minute and ask again.</p>`,
  error: `<p>The assistant could not answer just now. Please try again.</p>`,
  invalid: `<p>I could not read that question. Please ask it in a sentence or two (up to ${MAX_QUESTION} characters).</p>`,
  tooLong: `<p>That question is too long for me: the limit is ${MAX_QUESTION} characters. Please shorten it to a sentence or two.</p>`,
}
