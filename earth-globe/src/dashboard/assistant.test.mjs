import test from "node:test"
import assert from "node:assert/strict"
import { askAssistant, renderAnswer } from "./assistant.js"

const resp = (status, body) => async () => new Response(body === undefined ? null : JSON.stringify(body), { status })

test("model text is escaped, never inserted as HTML", () => {
  const html = renderAnswer({
    answer_md: `<img src=x onerror=alert(1)>\n\nsecond <b>para</b>`,
    claims: [{ text: `<script>alert(2)</script>`, source_ns: [1] }],
    sources: [{ n: 1, id: "a", citation: `Cite <i>x</i>`, doi: null, url: null }],
    data_used: [{ site_id: `<s>`, variable: "v", from: "2026-01-01", to: "2026-01-02", products: ["MUR v4"] }],
    confidence: "low",
    abstained: false,
  })
  assert.ok(!/<img|<script|<b>|<i>|<s>/.test(html), html)
  assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt;/)
  assert.match(html, /<sup class="cite">\[1\]<\/sup>/)
})

test("only https links become clickable; a DOI becomes a doi.org link", () => {
  const a = (s) => renderAnswer({ answer_md: "x", claims: [], data_used: [], sources: [{ n: 1, id: "a", citation: "C", ...s }], abstained: false })
  assert.ok(!a({ url: "javascript:alert(1)" }).includes("href="))
  assert.ok(!a({ url: "http://insecure.example" }).includes("href="))
  assert.match(a({ url: "https://example.org/p" }), /href="https:\/\/example\.org\/p"/)
  assert.match(a({ doi: "10.1000/x y" }), /href="https:\/\/doi\.org\/10\.1000\/x%20y"/)
  assert.match(a({ url: "https://e.org/\"onmouseover=\"x" }), /href="https:\/\/e\.org\/&quot;onmouseover=&quot;x"/)
})

test("an abstained answer says so", () => {
  assert.match(renderAnswer({ answer_md: "No.", claims: [], sources: [], data_used: [], abstained: true }), /Not enough evidence/)
})

test("client maps statuses: 503, 404 and network errors fall back; 429 does not", async () => {
  assert.deepEqual(await askAssistant("q", {}, resp(503, { error: "assistant_unavailable" })), { ok: false, reason: "unavailable", why: undefined })
  assert.deepEqual(await askAssistant("q", {}, resp(503, { error: "assistant_unavailable", reason: "quota" })), { ok: false, reason: "unavailable", why: "quota" })
  assert.deepEqual(await askAssistant("q", {}, resp(404)), { ok: false, reason: "unavailable", why: undefined })
  assert.deepEqual(await askAssistant("q", {}, async () => { throw new TypeError("offline") }), { ok: false, reason: "unavailable" })
  assert.deepEqual(await askAssistant("q", {}, resp(429, {})), { ok: false, reason: "limited" })
  assert.deepEqual(await askAssistant("q", {}, resp(400, { error: "bad_question" })), { ok: false, reason: "invalid" })
  assert.deepEqual(await askAssistant("q", {}, resp(502, {})), { ok: false, reason: "error" })
  assert.deepEqual(await askAssistant("q", {}, resp(200, { answer_md: "a" })), { ok: true, data: { answer_md: "a" } })
})

import { renderMarkdown } from "./assistant.js"

test("markdown: bold, lists, headings and line breaks become tags", () => {
  const html = renderMarkdown("Intro line\nsecond line\n\n**Summary:**\n- Min: 25.97 °C\n- Max: 30.04 °C\n\n1. First\n2. Second\n\n## Heading\nUse `x` here.")
  assert.equal(
    html,
    "<p>Intro line<br>second line</p><p><strong>Summary:</strong></p><ul><li>Min: 25.97 °C</li><li>Max: 30.04 °C</li></ul><ol><li>First</li><li>Second</li></ol><p><strong>Heading</strong></p><p>Use <code>x</code> here.</p>",
  )
})

test("markdown: nothing from the text can become markup", () => {
  const nasty = [
    "<img src=x onerror=alert(1)>",
    "**<script>alert(1)</script>**",
    "- <b onmouseover=x>item</b>",
    "[click](javascript:alert(1))",
    "![x](https://e.org/x.png)",
    "`</code><img src=x onerror=1>`",
    "# <iframe src=//e.org>",
  ].join("\n\n")
  const html = renderMarkdown(nasty)
  // Every "<" in the output must open or close one of the few tags we generate, with no attributes.
  assert.ok(!/<(?!\/?(p|strong|em|code|ul|ol|li|br)>)/.test(html), html)
  // Links and images are not supported: the source text stays visible as inert text.
  assert.ok(html.includes("[click](javascript:alert(1))") && html.includes("![x](https://e.org/x.png)"), html)
  assert.ok(html.includes("&lt;img src=x onerror=alert(1)&gt;"), html)
})

test("markdown: unmatched markers and tables stay as text", () => {
  assert.equal(renderMarkdown("a ** b"), "<p>a ** b</p>")
  assert.equal(renderMarkdown("| a | b |\n|---|---|"), "<p>| a | b |<br>|---|---|</p>")
  assert.equal(renderMarkdown(""), "")
  assert.equal(renderMarkdown("one\n\n\n\ntwo"), "<p>one</p><p>two</p>")
})

test("markdown: *italic* for species names, without catching stars that are not italics", () => {
  assert.equal(renderMarkdown("for *Kappaphycus alvarezii* in Indonesia"), "<p>for <em>Kappaphycus alvarezii</em> in Indonesia</p>")
  assert.equal(renderMarkdown("**bold** and *it*"), "<p><strong>bold</strong> and <em>it</em></p>")
  assert.equal(renderMarkdown("2 * 3 * 4"), "<p>2 * 3 * 4</p>") // spaces inside: arithmetic, not italics
  assert.equal(renderMarkdown("a*b*c"), "<p>a*b*c</p>") // inside a word
  assert.equal(renderMarkdown("*<img src=x onerror=1>*"), "<p><em>&lt;img src=x onerror=1&gt;</em></p>") // still escaped
  assert.equal(renderMarkdown("* item one\n* item two"), "<ul><li>item one</li><li>item two</li></ul>") // list bullets stay lists
})

test("the over-length message states the limit", async () => {
  const { MESSAGES, MAX_QUESTION } = await import("./assistant.js")
  assert.equal(MAX_QUESTION, 500)
  assert.match(MESSAGES.tooLong, /500 characters/)
  assert.match(MESSAGES.invalid, /500 characters/)
})
