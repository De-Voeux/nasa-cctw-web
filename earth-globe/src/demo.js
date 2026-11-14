import { EarthGlobe } from "./earth/EarthGlobe.js"
import albedo from "./assets/earth/albedo.jpg"
import bump from "./assets/earth/bump.jpg"
import ocean from "./assets/earth/ocean.png"
import clouds from "./assets/earth/clouds.jpg"
import lights from "./assets/earth/lights.png"
import sky from "./assets/earth/sky.jpg"

// Tuning from the URL, e.g. ?softness=0 (hard terminator) or ?softness=0.3&ambient=0.03.
// Only keys that are present are passed: an explicit undefined would override a default.
const query = new URLSearchParams(location.search)
const tuning = {}
for (const [param, option] of [["softness", "terminatorSoftness"], ["ambient", "ambient"]]) {
  if (query.has(param) && Number.isFinite(Number(query.get(param)))) tuning[option] = Number(query.get(param))
}

const globe = new EarthGlobe(document.getElementById("container"), {
  textures: { albedo, bump, ocean, clouds, lights, sky },
  // These cloud maps store density as brightness, not in an alpha channel.
  cloudsFormat: "luminance",
  ...tuning,
})

const readout = document.getElementById("readout")
const clicked = document.getElementById("clicked")
const spin = document.getElementById("spin")
let spinning = true

const fmt = (n, d = 2) => (n >= 0 ? " " : "") + n.toFixed(d)
globe.on("viewchange", ({ lat, lon, altitude }) => {
  readout.textContent = `lat ${fmt(lat)}\nlon ${fmt(lon)}\nalt ${altitude.toFixed(2)} R`
})
globe.on("select", ({ lat, lon }) => {
  clicked.textContent = `clicked: ${lat.toFixed(2)}, ${lon.toFixed(2)}`
})
globe.on("error", (err) => {
  readout.textContent = String(err.message || err)
})

for (const b of document.querySelectorAll("[data-fly]")) {
  b.addEventListener("click", () => {
    const [lat, lon, altitude] = b.dataset.fly.split(",").map(Number)
    spinning = false
    spin.textContent = "Auto-rotate: off"
    globe.flyTo({ lat, lon, altitude })
  })
}
spin.addEventListener("click", () => {
  spinning = !spinning
  globe.setAutoRotate(spinning)
  spin.textContent = `Auto-rotate: ${spinning ? "on" : "off"}`
})

// Handy in the browser console while developing: window.globe.getView()
window.globe = globe
