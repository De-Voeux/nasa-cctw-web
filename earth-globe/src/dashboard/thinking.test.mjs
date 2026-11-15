import test from "node:test"
import assert from "node:assert/strict"
import { thinkingLabel, thinkingHtml, startThinking } from "./thinking.js"

test("the words change as the wait gets longer", () => {
  assert.equal(thinkingLabel(0), "Thinking")
  assert.equal(thinkingLabel(7.9), "Thinking")
  assert.equal(thinkingLabel(8), "Still thinking")
  assert.equal(thinkingLabel(19.9), "Still thinking")
  assert.match(thinkingLabel(20), /^Still working/)
})

test("the markup announces itself politely and hides the decorative dots from screen readers", () => {
  const html = thinkingHtml()
  assert.match(html, /role="status"/)
  assert.match(html, /aria-live="polite"/)
  assert.match(html, /class="th-dots" aria-hidden="true"/)
  assert.match(html, /<span class="th-label">Thinking<\/span>/)
})

test("startThinking updates the label every second and stops when told to", () => {
  let t = 0
  let tick
  let cleared = false
  const label = { textContent: "Thinking" }
  const bubble = { querySelector: (s) => (s === ".th-label" ? label : null) }
  const stop = startThinking(bubble, () => t, (fn) => ((tick = fn), 42), (id) => { cleared = id === 42 })
  t = 9000
  tick()
  assert.equal(label.textContent, "Still thinking")
  t = 25000
  tick()
  assert.match(label.textContent, /^Still working/)
  stop()
  assert.equal(cleared, true)
})

test("a bubble that was already replaced by the answer is left alone", () => {
  let tick
  const bubble = { querySelector: () => null }
  startThinking(bubble, () => 0, (fn) => ((tick = fn), 1), () => {})
  assert.doesNotThrow(() => tick())
})
