/**
 * HTML elements pinned to lat/lon on the three.js globe.
 * Positions update on the globe's "frame" event (after each render), so they
 * never lag the drawn Earth. Items on the far side or near the horizon fade out.
 */
export class GlobeOverlay {
  constructor(globe, layer) {
    this.globe = globe
    this.layer = layer
    this.items = []
    this._p = {}
    globe.on("frame", () => this.update())
  }

  /**
   * @param {{lat:number, lon:number, el:HTMLElement, group?:string, minFacing?:number}} item
   *   minFacing: hide below this facing cosine (0 = horizon). Higher hides earlier.
   */
  add(item) {
    const it = { minFacing: 0.12, hidden: false, ...item }
    it.el.style.position = "absolute"
    this.layer.append(it.el)
    this.items.push(it)
    return it
  }

  /** Show or hide every item in a group (e.g. "markers", "labels"). */
  setGroupVisible(group, visible) {
    for (const it of this.items) if (it.group === group) it.hidden = !visible
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
        }
        continue
      }
      if (it._shown !== true) {
        it.el.style.visibility = "visible"
        it._shown = true
      }
      it.el.style.transform = `translate3d(${p.x.toFixed(1)}px, ${p.y.toFixed(1)}px, 0) translate(-50%, -50%)`
      // fade in over a short band just above the cut-off
      it.el.style.opacity = Math.min(1, (p.facing - it.minFacing) * 8).toFixed(2)
    }
  }
}
