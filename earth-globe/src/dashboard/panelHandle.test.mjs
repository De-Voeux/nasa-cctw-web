import test from "node:test"
import assert from "node:assert/strict"
import { shouldHide, velocityOf, FLICK, FLICK_MIN_TRAVEL, DRAG_THRESHOLD } from "./panelHandle.js"

const W = 424

test("released past halfway, the panel hides; before halfway, it stays open", () => {
  assert.equal(shouldHide(W * 0.51, W, 0), true)
  assert.equal(shouldHide(W * 0.49, W, 0), false)
  assert.equal(shouldHide(0, W, 0), false)
  assert.equal(shouldHide(W, W, 0), true)
})

test("a quick flick decides the direction whatever the position", () => {
  assert.equal(shouldHide(40, W, FLICK + 0.1), true) // flicked toward hidden from almost open
  assert.equal(shouldHide(W - 40, W, -(FLICK + 0.1)), false) // flicked back toward open from almost hidden
  assert.equal(shouldHide(W * 0.9, W, FLICK - 0.1), true) // too slow to be a flick: position decides
  // a fast but tiny movement (a click with a slip of the hand) is not a flick: position decides
  assert.equal(shouldHide(10, W, -(FLICK + 1), 10), false)
  assert.equal(shouldHide(W - 10, W, FLICK + 1, 10), true)
  assert.equal(shouldHide(FLICK_MIN_TRAVEL, W, FLICK + 1, FLICK_MIN_TRAVEL), true)
})

test("velocity uses roughly the last 100 ms of samples", () => {
  assert.equal(velocityOf([]), 0)
  assert.equal(velocityOf([{ t: 0, x: 0 }]), 0)
  // 200 px in the last 100 ms = 2 px/ms; the older slow part is ignored
  assert.equal(velocityOf([{ t: 0, x: 0 }, { t: 400, x: 10 }, { t: 450, x: 110 }, { t: 500, x: 210 }]), (210 - 10) / (500 - 400))
  assert.equal(velocityOf([{ t: 0, x: 300 }, { t: 100, x: 100 }]), -2) // leftwards is negative
  assert.equal(velocityOf([{ t: 5, x: 0 }, { t: 5, x: 50 }]), 0) // no time passed: no division by zero
})

test("a press must travel a few pixels before it is a drag", () => {
  assert.ok(DRAG_THRESHOLD >= 3 && DRAG_THRESHOLD <= 10)
})
