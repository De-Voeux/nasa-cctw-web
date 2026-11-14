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
import { LEVELS, LEVEL_ORDER, assess } from "../data/stress.js"
import { GlobeOverlay } from "./overlay.js"
import { mountDatePills } from "./datePills.js"
import { SidePanel } from "./sidePanel.js"
import { FilterMenu } from "./filterMenu.js"
import { mountFlags } from "./flags.js"
import { Chat } from "./chat.js"
import { answer } from "./ask.js"
import { waveIcon, thermometerIcon, dropletIcon, rainIcon } from "./icons.js"
import { initLayout } from "./layout.js"

const HOME = { lat: 5, lon: 117, altitude: 1.35 }
const EXAMPLE_QUESTION = "Which area has the most ice-ice case?"
const DEFAULT_SPECIES = "Kappaphycus alvarezii"
const DEFAULT_COUNTRY = "Indonesia"
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

// --------------------------------------------------------------- data and filters

const byId = new Map(LOCATIONS.map((l) => [l.id, l]))
// The assessment of every place. None exists yet, so all are "Insufficient Data" (see data/stress.js).
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

// --------------------------------------------------------------- overlay

const overlay = new GlobeOverlay(globe, $("overlay"))

// Country and sea names: the lowest priority, so they step aside for pins and pin names.
for (const l of PLACE_LABELS) {
  const el = document.createElement("span")
  el.className = `place-label${l.sea ? " sea" : ""}`
  el.textContent = l.text
  overlay.add({ lat: l.lat, lon: l.lon, el, group: "labels", minFacing: 0.25, declutter: true, priority: -1 })
}

const pins = new Map() // id -> { marker, name, el, nameEl }
for (const loc of LOCATIONS) {
  const el = document.createElement("button")
  el.className = "marker"
  el.setAttribute("aria-label", `${loc.name}, ${loc.country}: ${loc.concern} mentioned for ${loc.taxa.length} taxa`)
  el.setAttribute("aria-pressed", "false")
  el.innerHTML = waveIcon + (loc.taxa.length > 1 ? `<span class="count">${loc.taxa.length}</span>` : "")
  el.addEventListener("click", () => select(loc.id))
  const nameEl = document.createElement("span")
  nameEl.className = "place-label marker-name"
  nameEl.textContent = loc.name
  const marker = overlay.add({ lat: loc.lat, lon: loc.lon, el, group: "markers", minFacing: 0.15, solid: true })
  // The name sits under its pin (dy), and is hidden when it would land on another pin or name.
  const name = overlay.add({ lat: loc.lat, lon: loc.lon, el: nameEl, group: "names", minFacing: 0.15, declutter: true, dy: 36, priority: loc.taxa.length })
  pins.set(loc.id, { marker, name, el, nameEl })
}

let selectedId = null

function setPressed(id) {
  selectedId = id
  for (const [k, p] of pins) {
    p.el.setAttribute("aria-pressed", String(k === id))
    p.el.style.zIndex = k === id ? "2" : ""
    p.name.priority = (byId.get(k).taxa.length || 0) + (k === id ? 1000 : 0)
  }
}

// Pins of other species are hidden; pins that fail another filter stay but fade.
function paintPins() {
  for (const [id, p] of pins) {
    const loc = byId.get(id)
    const show = hasSpecies(loc)
    overlay.setHidden(p.marker, !show)
    overlay.setHidden(p.name, !show)
    const dim = !passes(loc)
    p.el.classList.toggle("is-dim", dim)
    p.nameEl.classList.toggle("is-dim", dim)
  }
}

// --------------------------------------------------------------- panel

const panel = new SidePanel($("panel-body"), {
  root: document.querySelector(".side-panel"),
  onSelect: (id) => select(id),
  onBack: () => deselect(),
})

function select(id) {
  const loc = byId.get(id)
  if (!loc) return
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

// --------------------------------------------------------------- ask bar and conversation

const chat = new Chat({
  bar: $("ask-bar"),
  panel: $("chat"),
  log: $("chat-log"),
  closeBtn: $("chat-close"),
  onGoto: (id) => select(id),
})

$("ask").addEventListener("submit", (e) => {
  e.preventDefault()
  const input = $("ask-input")
  const q = input.value.trim() || EXAMPLE_QUESTION
  input.value = ""
  chat.user(q)
  const res = answer(q, LOCATIONS)
  chat.bot(res.html)
  if (!res.focus) return
  if (res.openDetail) return select(res.focus.id)
  setPressed(res.focus.id)
  globe.flyTo({ lat: res.focus.lat, lon: res.focus.lon, altitude: 0.9, duration: 1600 })
})

// --------------------------------------------------------------- controls

function zoomBy(factor) {
  const v = globe.getView()
  globe.flyTo({ lat: v.lat, lon: v.lon, altitude: v.altitude * factor, duration: 450 })
}
$("zoom-in").addEventListener("click", () => zoomBy(0.65))
$("zoom-out").addEventListener("click", () => zoomBy(1.5))
$("zoom-home").addEventListener("click", () => globe.flyTo({ ...HOME, duration: 1600 }))

// The data layers. None is connected yet, so each row says so instead of offering a switch.
const LAYERS = [
  { name: "Sea Water Temperature", source: "NASA GHRSST MUR L4 · 0.01°", icon: thermometerIcon },
  { name: "Salinity", source: "Copernicus Global Ocean Physics · 0.083°", icon: dropletIcon },
  { name: "Rainfall", source: "NASA GPM IMERG · Open-Meteo forecast", icon: rainIcon },
]

const layersBtn = $("layers-btn")
const layersMenu = $("layers-menu")
layersMenu.innerHTML = `
  <h2>Layers</h2>
  <ul class="layer-list">
    ${LAYERS.map(
      (l) => `
      <li class="layer-row">
        <span class="lr-icon">${l.icon}</span>
        <span class="lr-text"><span class="lr-name">${l.name}</span><span class="lr-src">${l.source}</span></span>
        <span class="lr-state">Not connected yet</span>
      </li>`,
    ).join("")}
  </ul>`

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
