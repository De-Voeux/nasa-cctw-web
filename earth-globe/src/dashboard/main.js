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
import { LEVELS, LEVEL_ORDER, DEMO, assess } from "../data/stress.js"
import { assessmentFor, loadEnvironment } from "../data/environment.js"
import { GlobeOverlay } from "./overlay.js"
import { mountDatePills } from "./datePills.js"
import { SidePanel } from "./sidePanel.js"
import { FilterMenu } from "./filterMenu.js"
import { mountFlags } from "./flags.js"
import { mountChat } from "./chat.js"
import { mountPanelHandle } from "./panelHandle.js"
import { mountLayersMenu } from "./layersMenu.js"

const HOME = { lat: 5, lon: 117, altitude: 1.35 }
const DEFAULT_SPECIES = "Kappaphycus alvarezii"
const DEFAULT_COUNTRY = "Indonesia"
const $ = (id) => document.getElementById(id)

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

// --------------------------------------------------------------- data and filters (sidebar, Radit)

const byId = new Map(LOCATIONS.map((l) => [l.id, l]))
// The assessment of every place. None exists yet; see data/stress.js for the demo levels.
const assessments = new Map(LOCATIONS.map((l) => [l.id, assess(l)]))

// Every taxon named in the leads, the MVP candidate first.
const SPECIES = [...new Set(LOCATIONS.flatMap((l) => l.taxa))].sort((a, b) =>
  a === DEFAULT_SPECIES ? -1 : b === DEFAULT_SPECIES ? 1 : a.localeCompare(b),
)

const state = {
  species: DEFAULT_SPECIES,
  country: DEFAULT_COUNTRY, // null = all countries
  regions: null, // Set of ids applied by the Regions filter, null = all
  levels: new Set(LEVEL_ORDER),
  sort: "low", // "low" = lowest risk first, "high" = highest risk first
  text: "",
}

const hasSpecies = (l) => l.taxa.includes(state.species)
// Places the Regions menu can offer: the chosen species in the chosen country.
const inScope = (l) => hasSpecies(l) && (!state.country || l.country === state.country)
const matchesText = (l) => !state.text || `${l.name} ${l.country} ${l.note || ""} ${l.taxa.join(" ")}`.toLowerCase().includes(state.text)
const passes = (l) =>
  inScope(l) && (!state.regions || state.regions.has(l.id)) && state.levels.has(assessments.get(l.id).level) && matchesText(l)

function rows() {
  const rank = (l) => LEVELS[assessments.get(l.id).level].rank
  const insufficient = (l) => assessments.get(l.id).level === "insufficient"
  return LOCATIONS.filter(passes)
    .sort((a, b) => {
      // "No data" always goes last, whichever way the list is sorted.
      if (insufficient(a) !== insufficient(b)) return insufficient(a) ? 1 : -1
      const d = state.sort === "low" ? rank(a) - rank(b) : rank(b) - rank(a)
      return d || a.name.localeCompare(b.name)
    })
    .map((loc) => ({ loc, a: assessments.get(loc.id) }))
}

// --------------------------------------------------------------- overlay (markers with level icons)

const overlay = new GlobeOverlay(globe, $("overlay"))

for (const l of PLACE_LABELS) {
  const el = document.createElement("span")
  el.className = `place-label${l.sea ? " sea" : ""}`
  el.textContent = l.text
  overlay.add({ lat: l.lat, lon: l.lon, el, group: "labels", minFacing: 0.25, declutter: true, priority: -1 })
}

/** id → { el, item } */
const pins = new Map()
for (const loc of LOCATIONS) {
  const a = assessments.get(loc.id)
  const lv = LEVELS[a.level]
  const el = document.createElement("button")
  el.className = "marker"
  el.dataset.level = a.level
  el.setAttribute("aria-pressed", "false")
  el.setAttribute("aria-label", `${loc.name}, ${loc.country}: ${lv.label}`)
  el.innerHTML = `<span class="marker-dot"><img src="${lv.icon}" alt="" draggable="false"></span><span class="marker-name">${loc.name}</span>`
  el.addEventListener("click", () => select(loc.id))
  const item = overlay.add({ lat: loc.lat, lon: loc.lon, el, group: "markers", minFacing: 0.15, solid: true })
  pins.set(loc.id, { el, item })
}

function setPressed(id) {
  for (const [k, p] of pins) {
    p.el.setAttribute("aria-pressed", String(k === id))
    p.el.style.zIndex = k === id ? "2" : ""
  }
}

// Pins of other species are hidden; pins that fail another filter stay but fade.
function paintPins() {
  for (const [id, p] of pins) {
    const loc = byId.get(id)
    overlay.setHidden(p.item, !hasSpecies(loc))
    p.el.classList.toggle("is-dim", !passes(loc))
  }
}

// --------------------------------------------------------------- side panel (Radit)

const panel = new SidePanel($("panel-body"), {
  root: document.querySelector(".side-panel"),
  onSelect: (id) => select(id),
  onBack: () => deselect(),
})

function select(id) {
  const loc = byId.get(id)
  if (!loc) return
  setPanel(false, false) // a place was picked: bring the panel back
  setBody(false, false) // a place was picked: show its details, but keep the remembered choice
  setSheet(true)
  setPressed(id)
  panel.showLocation(loc, assessments.get(id))
  const alt = Math.min(globe.getView().altitude, 0.7)
  globe.flyTo({ lat: loc.lat, lon: loc.lon, altitude: alt, duration: 1600 })
}

function deselect() {
  setPressed(null)
  panel.showList(rows())
}

/** Redraw the list and the pins after any filter changed. */
function refresh() {
  setPressed(null)
  paintPins()
  panel.showList(rows())
}

const dates = mountDatePills($("dates"), { onChange: (d) => panel.setDay(d) })
panel.day = dates.current

// Species
const speciesSelect = $("species")
speciesSelect.innerHTML = SPECIES.map((s) => `<option value="${s}">${s}</option>`).join("")
speciesSelect.value = state.species

// Regions and Stress Level filters
const regionsMenu = new FilterMenu($("regions-chip"), {
  label: "Regions",
  onApply: (selected) => {
    state.regions = selected.size === regionsMenu.options.length ? null : selected
    refresh()
  },
})
const levelsMenu = new FilterMenu($("levels-chip"), {
  label: "Stress Level",
  onApply: (selected) => {
    state.levels = selected
    refresh()
  },
})
levelsMenu.setOptions(
  LEVEL_ORDER.map((k) => ({ value: k, label: LEVELS[k].label })),
  state.levels,
)

/** The Regions menu lists the places of the chosen species in the chosen country. */
function offerRegions() {
  const scope = LOCATIONS.filter(inScope).sort((a, b) => a.name.localeCompare(b.name))
  state.regions = null
  regionsMenu.setOptions(
    scope.map((l) => ({ value: l.id, label: state.country ? l.name : `${l.name} · ${l.country}` })),
    new Set(scope.map((l) => l.id)),
  )
}

speciesSelect.addEventListener("change", () => {
  state.species = speciesSelect.value
  offerRegions()
  refresh()
})

mountFlags($("flags"), {
  selected: state.country,
  onChange: (country) => {
    state.country = country
    offerRegions()
    refresh()
  },
})

// Sort
$("sort-btn").addEventListener("click", () => {
  state.sort = state.sort === "low" ? "high" : "low"
  const lowest = state.sort === "low"
  $("sort-label").textContent = lowest ? "Lowest Risk" : "Highest Risk"
  $("sort-btn").setAttribute("aria-label", `Sort order: ${lowest ? "lowest" : "highest"} risk first`)
  refresh()
})

$("search").addEventListener("input", (e) => {
  state.text = e.target.value.trim().toLowerCase()
  refresh()
})

offerRegions()
paintPins()
panel.showList(rows())

if (!DEMO) {
  loadEnvironment()
    .then((payload) => {
      for (const loc of LOCATIONS) assessments.set(loc.id, assessmentFor(loc, payload))
      refresh()
    })
    .catch((error) => console.warn("SEAmon environmental data unavailable", error))
}

// Collapse button: hides the list / details so more of the map shows. The choice is remembered
// in this browser only; storage may be blocked, so it is optional.
const sidePanelEl = document.querySelector(".side-panel")
const bodyBtn = $("body-collapse")
function setBody(collapsed, remember = true) {
  sidePanelEl.dataset.body = collapsed ? "collapsed" : "open"
  bodyBtn.setAttribute("aria-expanded", String(!collapsed))
  bodyBtn.setAttribute("aria-label", `${collapsed ? "Show" : "Hide"} ${sidePanelEl.dataset.mode === "detail" ? "details" : "list"}`)
  if (!remember) return
  try {
    localStorage.setItem("seamon.panelBody", collapsed ? "collapsed" : "open")
  } catch {}
}
let savedBody = null
try {
  savedBody = localStorage.getItem("seamon.panelBody")
} catch {}
setBody(savedBody === "collapsed", false)
bodyBtn.addEventListener("click", () => setBody(sidePanelEl.dataset.body !== "collapsed"))
// The label says "list" or "details" depending on what the panel shows.
new MutationObserver(() => setBody(sidePanelEl.dataset.body === "collapsed", false)).observe(sidePanelEl, { attributes: true, attributeFilter: ["data-mode"] })

// One handle hides the whole panel (wide screens) and brings it back. Click it, press the arrow keys,
// or drag it (dashboard/panelHandle.js); it travels with the panel and its arrow turns around.
const panelToggle = $("panel-toggle")
const isPanelHidden = () => document.documentElement.dataset.panel === "hidden"
function setPanel(hidden, remember = true) {
  document.documentElement.dataset.panel = hidden ? "hidden" : "open"
  panelToggle.dataset.look = hidden ? "hidden" : "open"
  panelToggle.setAttribute("aria-expanded", String(!hidden))
  panelToggle.setAttribute("aria-label", hidden ? "Show panel" : "Hide panel")
  panelToggle.title = hidden ? "Show locations panel (drag or click)" : "Hide panel (drag or click)"
  if (!remember) return
  try {
    localStorage.setItem("seamon.panelHidden", hidden ? "1" : "0")
  } catch {}
}
/** A change made by the user: also gives the tab a short nudge once the panel has gone. */
function userSetPanel(hidden) {
  if (hidden === isPanelHidden()) return
  setPanel(hidden)
  panelToggle.classList.remove("nudge")
  if (hidden) {
    void panelToggle.offsetWidth // restart the animation
    panelToggle.classList.add("nudge")
  }
}
let savedHidden = null
try {
  savedHidden = localStorage.getItem("seamon.panelHidden")
} catch {}
setPanel(savedHidden === "1", false)
mountPanelHandle({ handle: panelToggle, panel: sidePanelEl, isHidden: isPanelHidden, setHidden: userSetPanel })
panelToggle.addEventListener("click", () => userSetPanel(!isPanelHidden()))

// --------------------------------------------------------------- bottom sheet (phones)

/** Must match the bottom-sheet media query in dashboard.css. */
const SHEET = matchMedia("(max-width: 600px), (orientation: portrait) and (max-width: 900px)")
const handle = $("sheet-handle")

function setSheet(expanded) {
  document.body.dataset.sheet = expanded && SHEET.matches ? "expanded" : "collapsed"
  const open = document.body.dataset.sheet === "expanded"
  handle.setAttribute("aria-expanded", String(open))
  handle.setAttribute("aria-label", open ? "Show less of the list" : "Show more of the list")
}
setSheet(false)
SHEET.addEventListener("change", () => setSheet(false))
handle.addEventListener("click", () => setSheet(document.body.dataset.sheet !== "expanded"))
// Using the search, species, flags or filters needs room: open the sheet.
document.querySelector(".side-panel").addEventListener("focusin", (e) => {
  if (e.target !== handle) setSheet(true)
})
// Swipe the handle up or down.
let touchY = null
handle.addEventListener("touchstart", (e) => (touchY = e.touches[0].clientY), { passive: true })
handle.addEventListener("touchend", (e) => {
  if (touchY === null) return
  const dy = e.changedTouches[0].clientY - touchY
  if (Math.abs(dy) > 30) setSheet(dy < 0)
  touchY = null
})

// --------------------------------------------------------------- chat

mountChat($("chat"), {
  locations: LOCATIONS,
  onShow: (loc) => select(loc.id),
  getContext: () => ({ species: state.species, country: state.country }),
})

// --------------------------------------------------------------- controls

function zoomBy(factor) {
  const v = globe.getView()
  globe.flyTo({ lat: v.lat, lon: v.lon, altitude: v.altitude * factor, duration: 450 })
}
$("zoom-in").addEventListener("click", () => zoomBy(0.65))
$("zoom-out").addEventListener("click", () => zoomBy(1.5))
$("brand").addEventListener("click", () => {
  deselect()
  globe.flyTo({ ...HOME, duration: 1600 })
})

mountLayersMenu($("layers-btn"), $("layers-menu"))
