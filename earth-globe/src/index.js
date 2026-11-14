import { EarthGlobe } from "./earth/EarthGlobe.js"
import albedo from "./assets/earth/albedo.jpg"
import normal from "./assets/earth/normal.jpg"
import ocean from "./assets/earth/ocean.jpg"
import clouds from "./assets/earth/clouds.png"
import lights from "./assets/earth/lights.png"

const globe = new EarthGlobe(document.getElementById("container"), {
  textures: { albedo, normal, ocean, clouds, lights },
  // The placeholder cloud PNG keeps cloud density in its alpha channel.
  // NASA's Blue Marble cloud map stores it as brightness: use "luminance".
  cloudsFormat: "alpha",
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
