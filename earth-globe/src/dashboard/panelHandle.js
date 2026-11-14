/**
 * Drag behaviour of the panel handle (the "Locations" tab on the panel's left edge).
 *
 * Dragging moves the panel and the handle together, following the pointer between fully open
 * and fully hidden. On release the panel snaps to whichever side it was heading for (a quick
 * flick counts, however short). A press that barely moves is a click: it toggles, as before.
 * Left and right arrow keys also hide and show it.
 */

/** Pixels the pointer must travel before a press becomes a drag. */
export const DRAG_THRESHOLD = 8
/** px per ms: a flick faster than this decides the direction regardless of position. */
export const FLICK = 0.4
/** A flick only counts after this much travel, so a click with a slip of the hand is not mistaken for one. */
export const FLICK_MIN_TRAVEL = 30

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v))

/**
 * @param {number} x         panel offset when released: 0 = open, `width` = hidden
 * @param {number} width     distance between open and hidden
 * @param {number} velocity  px per ms, positive toward hidden
 * @param {number} travel    how far the pointer moved in total, px
 * @returns {boolean} true to hide
 */
export function shouldHide(x, width, velocity, travel = Infinity) {
  if (Math.abs(velocity) > FLICK && travel >= FLICK_MIN_TRAVEL) return velocity > 0
  return x > width / 2
}

/** Velocity over roughly the last 100 ms of pointer samples ({t, x}), px per ms. */
export function velocityOf(samples) {
  if (samples.length < 2) return 0
  const last = samples[samples.length - 1]
  const first = samples.find((s) => last.t - s.t <= 100) ?? samples[samples.length - 2]
  const dt = last.t - first.t
  return dt > 0 ? (last.x - first.x) / dt : 0
}

/**
 * @param {{handle:HTMLElement, panel:HTMLElement, root?:HTMLElement,
 *          isHidden:()=>boolean, setHidden:(hidden:boolean)=>void}} o
 */
export function mountPanelHandle({ handle, panel, root = document.documentElement, isHidden, setHidden }) {
  const arrow = handle.querySelector("svg")
  let drag = null
  let suppressClick = false

  // Registered first and in the capture phase, so a click that ends a drag never reaches the toggle.
  handle.addEventListener(
    "click",
    (e) => {
      if (!suppressClick) return
      suppressClick = false
      e.preventDefault()
      e.stopImmediatePropagation()
    },
    true,
  )

  handle.addEventListener("pointerdown", (e) => {
    if (e.button !== 0 || !e.isPrimary) return
    const gap = parseFloat(getComputedStyle(root).getPropertyValue("--gap")) || 12
    const panelW = panel.offsetWidth
    const width = panelW + gap * 2
    drag = {
      id: e.pointerId, startX: e.clientX, from: isHidden() ? width : 0,
      width, panelW, gap, moved: false, x: isHidden() ? width : 0, samples: [{ t: e.timeStamp, x: e.clientX }],
    }
    handle.setPointerCapture(e.pointerId)
  })

  function apply(x) {
    const { panelW, gap, width } = drag
    panel.style.transform = `translateX(${x}px)`
    handle.style.right = `${Math.max(0, panelW + gap - 1 - x)}px`
    if (arrow) arrow.style.transform = `rotate(${(180 * x) / width}deg)`
    handle.dataset.look = x > width / 2 ? "hidden" : "open"
  }

  handle.addEventListener("pointermove", (e) => {
    if (!drag || e.pointerId !== drag.id) return
    const dx = e.clientX - drag.startX
    if (!drag.moved) {
      if (Math.abs(dx) < DRAG_THRESHOLD) return
      drag.moved = true
      root.classList.add("panel-dragging")
      panel.style.visibility = "visible" // a hidden panel must be seen while it is pulled out
    }
    drag.x = clamp(drag.from + dx, 0, drag.width)
    drag.samples.push({ t: e.timeStamp, x: e.clientX })
    if (drag.samples.length > 8) drag.samples.shift()
    apply(drag.x)
  })

  function end(e) {
    if (!drag || e.pointerId !== drag.id) return
    const d = drag
    drag = null
    if (handle.hasPointerCapture?.(e.pointerId)) handle.releasePointerCapture(e.pointerId)
    if (!d.moved) return // a plain click: the click handler toggles
    suppressClick = e.type === "pointerup"
    const hide = e.type === "pointercancel" ? isHidden() : shouldHide(d.x, d.width, velocityOf(d.samples), Math.abs(d.x - d.from))
    // Hand the position back to the CSS states. The dragged values are flushed first, so the
    // slide to the final state starts where the pointer let go.
    void panel.offsetWidth
    panel.style.transform = ""
    panel.style.visibility = ""
    handle.style.right = ""
    if (arrow) arrow.style.transform = ""
    root.classList.remove("panel-dragging")
    setHidden(hide)
  }
  handle.addEventListener("pointerup", end)
  handle.addEventListener("pointercancel", end)

  handle.addEventListener("keydown", (e) => {
    if (e.key === "ArrowRight") (e.preventDefault(), setHidden(true))
    else if (e.key === "ArrowLeft") (e.preventDefault(), setHidden(false))
  })
}
