import { EarthGlobe } from "../earth/EarthGlobe.js"
import albedo from "../assets/earth/albedo.jpg"
import bump from "../assets/earth/bump.jpg"
import ocean from "../assets/earth/ocean.png"
// Clouds are off for now: they drift ~8 px/s against the pins, which read as the pins floating.
// To bring them back, uncomment this import, `clouds` in `textures` and `cloudsFormat` below,
// and put "Clouds," back in the credit line in index.html.
// import clouds from "../assets/earth/clouds.jpg"
import lights from "../assets/earth/lights.png"
import { LOCATIONS, PLACE_LABELS } from "../data/reportedLocations.js"
import { GlobeOverlay } from "./overlay.js"
import { mountDatePills } from "./datePills.js"
import { SidePanel } from "./sidePanel.js"
import { answer } from "./ask.js"
import { waveIcon } from "./icons.js"
import { initLayout } from "./layout.js"

const HOME = { lat: 5, lon: 117, altitude: 1.35 }
const EXAMPLE_QUESTION = "Which area has the most ice-ice reports?"
const $ = (id) => document.getElementById(id)

// --------------------------------------------------------------- layout

// Sizes the globe canvas before the globe is built, so it starts at the right
// resolution instead of jumping once the first frame is drawn.
initLayout()

// --------------------------------------------------------------- globe

const globe = new EarthGlobe($("globe"), {
  textures: { albedo, bump, ocean, /* clouds, */ lights },
  // cloudsFormat: "luminance", // these cloud maps store density as brightness
  background: null, // transparent: the CSS star field shows through
  initialView: { lat: 10, lon: 95, altitude: 3 },
  autoRotate: { enabled: false },
  minAltitude: 0.25,
  maxAltitude: 5,
})
window.globe = globe // handy in the console

globe.on("error", (err) => console.error(err))
globe.ready.then(() => globe.flyTo({ ...HOME, duration: 2400 }))

// --------------------------------------------------------------- overlay

const overlay = new GlobeOverlay(globe, $("overlay"))

for (const l of PLACE_LABELS) {
  const el = document.createElement("span")
  el.className = `place-label${l.sea ? " sea" : ""}`
  el.textContent = l.text
  overlay.add({ lat: l.lat, lon: l.lon, el, group: "labels", minFacing: 0.25 })
}

const markerEls = new Map()
for (const loc of LOCATIONS) {
  const el = document.createElement("button")
  el.className = "marker"
  el.setAttribute("aria-label", `${loc.name}, ${loc.country}: ${loc.concern} mentioned for ${loc.taxa.length} taxa`)
  el.setAttribute("aria-pressed", "false")
  el.innerHTML = waveIcon + (loc.taxa.length > 1 ? `<span class="count">${loc.taxa.length}</span>` : "")
  el.addEventListener("click", () => select(loc))
  markerEls.set(loc.id, el)
  overlay.add({ lat: loc.lat, lon: loc.lon, el, group: "markers", minFacing: 0.15 })
}

// --------------------------------------------------------------- panel

const panel = new SidePanel($("panel-body"), {
  locations: LOCATIONS,
  onSelect: (loc) => select(loc),
  onBack: () => deselect(),
})

function setPressed(id) {
  for (const [k, el] of markerEls) {
    el.setAttribute("aria-pressed", String(k === id))
    el.style.zIndex = k === id ? "2" : ""
  }
}

function select(loc) {
  setPressed(loc.id)
  panel.showLocation(loc)
  const alt = Math.min(globe.getView().altitude, 0.7)
  globe.flyTo({ lat: loc.lat, lon: loc.lon, altitude: alt, duration: 1600 })
}

function deselect() {
  setPressed(null)
  panel.showList()
}

const dates = mountDatePills($("dates"), { onChange: (d) => panel.setDay(d) })
panel.setDay(dates.current)
panel.showList()

$("search").addEventListener("input", (e) => {
  setPressed(null)
  panel.setFilter(e.target.value)
})

// links inside ask answers
$("panel-body").addEventListener("click", (e) => {
  const a = e.target.closest("[data-goto]")
  if (!a) return
  e.preventDefault()
  const loc = LOCATIONS.find((l) => l.id === a.dataset.goto)
  if (loc) select(loc)
})

// --------------------------------------------------------------- ask bar

$("ask").addEventListener("submit", (e) => {
  e.preventDefault()
  const input = $("ask-input")
  const q = input.value.trim() || EXAMPLE_QUESTION
  const res = answer(q, LOCATIONS)
  $("search").value = ""
  if (res.openDetail && res.focus) {
    select(res.focus)
  } else {
    setPressed(res.focus ? res.focus.id : null)
    panel.showAnswer(q, res.html)
    if (res.focus) globe.flyTo({ lat: res.focus.lat, lon: res.focus.lon, altitude: 0.9, duration: 1600 })
  }
  input.value = ""
})

// The long example question does not fit a phone: shorten the hint there, but
// keep the full question for an empty submit.
const askInput = $("ask-input")
function fitPlaceholder() {
  askInput.placeholder = window.innerWidth < 520 ? "Ask about the atlas" : EXAMPLE_QUESTION
}
fitPlaceholder()
window.addEventListener("resize", fitPlaceholder)

// --------------------------------------------------------------- controls

function zoomBy(factor) {
  const v = globe.getView()
  globe.flyTo({ lat: v.lat, lon: v.lon, altitude: v.altitude * factor, duration: 450 })
}
$("zoom-in").addEventListener("click", () => zoomBy(0.65))
$("zoom-out").addEventListener("click", () => zoomBy(1.5))
$("zoom-home").addEventListener("click", () => globe.flyTo({ ...HOME, duration: 1600 }))

const layersBtn = $("layers-btn")
const layersMenu = $("layers-menu")
layersMenu.innerHTML = `
  <h2>Layers</h2>
  <label><input type="checkbox" data-layer="markers" checked><span>Reported locations<small>Unverified research leads</small></span></label>
  <label><input type="checkbox" data-layer="labels" checked><span>Country & sea names</span></label>
  <label><input type="checkbox" data-layer="spin"><span>Auto-rotate</span></label>
  <h2 style="margin-top:12px">Environmental data</h2>
  <label style="opacity:.5;cursor:default"><input type="checkbox" disabled><span>Sea surface temperature<small>NASA MUR SST · not connected</small></span></label>
  <label style="opacity:.5;cursor:default"><input type="checkbox" disabled><span>Composite stress · 0.25°<small>Needs data pipeline</small></span></label>`

layersBtn.addEventListener("click", () => {
  const open = layersMenu.hidden
  layersMenu.hidden = !open
  layersBtn.setAttribute("aria-expanded", String(open))
})

function closeLayers() {
  layersMenu.hidden = true
  layersBtn.setAttribute("aria-expanded", "false")
}

// a tap outside the menu closes it, so the map controls are reachable again
document.addEventListener("pointerdown", (e) => {
  if (layersMenu.hidden) return
  if (layersMenu.contains(e.target) || layersBtn.contains(e.target)) return
  closeLayers()
})
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !layersMenu.hidden) {
    closeLayers()
    layersBtn.focus()
  }
})
layersMenu.addEventListener("change", (e) => {
  const k = e.target.dataset.layer
  if (k === "spin") globe.setAutoRotate(e.target.checked)
  else overlay.setGroupVisible(k, e.target.checked)
})
