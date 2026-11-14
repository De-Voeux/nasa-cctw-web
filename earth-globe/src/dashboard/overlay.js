/**
 * HTML elements pinned to lat/lon on the three.js globe.
 * Positions update on the globe's "frame" event (after each render), so they
 * never lag the drawn Earth. Items on the far side or near the horizon fade out.
 *
 * Decluttering: `solid` items (the markers) are always drawn and take up room.
 * `declutter` items (name labels) are placed one by one, highest `priority` first,
 * and hidden when their box overlaps something already placed.
 */
const PAD = 4 // px of breathing room around a label
const REMEASURE_EVERY = 30 // frames; webfonts and resizes change element sizes

export class GlobeOverlay {
  constructor(globe, layer) {
    this.globe = globe
    this.layer = layer
    this.items = []
    this._p = {}
    this._n = 0
    globe.on("frame", () => this.update())
  }

  /**
   * @param {{lat:number, lon:number, el:HTMLElement, group?:string, minFacing?:number,
   *   solid?:boolean, declutter?:boolean, priority?:number, dy?:number}} item
   *   minFacing: hide below this facing cosine (0 = horizon). Higher hides earlier.
   *   dy: px between the projected point and the centre of the element (a label under a marker).
   */
  add(item) {
    const it = { minFacing: 0.12, hidden: false, solid: false, declutter: false, priority: 0, dy: 0, ...item }
    it.el.style.position = "absolute"
    this.layer.append(it.el)
    this.items.push(it)
    return it
  }

  /** Show or hide every item in a group (e.g. "markers", "labels"). */
  setGroupVisible(group, visible) {
    for (const it of this.items) if (it.group === group) it.hidden = !visible
  }

  /** Show or hide one item. */
  setHidden(it, hidden) {
    it.hidden = hidden
  }

  update() {
    const rect = this.globe.renderer.domElement.getBoundingClientRect()
    const p = this._p
    for (const it of this.items) {
      this.globe.project(it.lat, it.lon, rect, p)
      const show = !it.hidden && p.facing > it.minFacing
      if (!show) {
        if (it._shown !== false) {
          it.el.style.visibility = "hidden"
          it._shown = false
          it._vis = undefined // the declutter pass decides again when it comes back
        }
        continue
      }
      if (it._shown !== true) {
        it.el.style.visibility = "visible"
        it._shown = true
        it._vis = undefined
      }
      it._x = p.x
      it._y = p.y
      it.el.style.transform = `translate3d(${p.x.toFixed(1)}px, ${p.y.toFixed(1)}px, 0) translate(-50%, -50%)`
      // fade in over a short band just above the cut-off
      it.el.style.opacity = Math.min(1, (p.facing - it.minFacing) * 8).toFixed(2)
    }
    this._declutter()
    this._n++
  }

  _box(it, pad = 0) {
    if (!it._w || this._n % REMEASURE_EVERY === 0) {
      it._w = it.el.offsetWidth
      it._h = it.el.offsetHeight
    }
    const cx = it._x
    const cy = it._y + it.dy
    return { l: cx - it._w / 2 - pad, r: cx + it._w / 2 + pad, t: cy - it._h / 2 - pad, b: cy + it._h / 2 + pad }
  }

  _declutter() {
    const placed = []
    for (const it of this.items) if (it.solid && it._shown) placed.push(this._box(it))
    const labels = this.items.filter((it) => it.declutter && it._shown).sort((a, b) => b.priority - a.priority)
    for (const it of labels) {
      const box = this._box(it, PAD)
      const clash = placed.some((o) => box.l < o.r && box.r > o.l && box.t < o.b && box.b > o.t)
      const vis = clash ? "hidden" : "visible"
      if (it._vis !== vis) {
        it.el.style.visibility = vis
        it._vis = vis
      }
      if (!clash) placed.push(box)
    }
  }
}
