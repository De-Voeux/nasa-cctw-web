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
  assert.deepEqual(await askAssistant("q", {}, resp(503, { error: "assistant_unavailable" })), { ok: false, reason: "unavailable" })
  assert.deepEqual(await askAssistant("q", {}, resp(404)), { ok: false, reason: "unavailable" })
  assert.deepEqual(await askAssistant("q", {}, async () => { throw new TypeError("offline") }), { ok: false, reason: "unavailable" })
  assert.deepEqual(await askAssistant("q", {}, resp(429, {})), { ok: false, reason: "limited" })
  assert.deepEqual(await askAssistant("q", {}, resp(502, {})), { ok: false, reason: "error" })
  assert.deepEqual(await askAssistant("q", {}, resp(200, { answer_md: "a" })), { ok: true, data: { answer_md: "a" } })
})
