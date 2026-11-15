import * as THREE from "three"
import { SST, SALINITY, RAIN } from "../data/gibsColormaps.js"

/**
 * Coloured ocean layers on the globe (sea temperature, salinity, rainfall).
 *
 * The data is a NASA GIBS map image of Southeast Asia for one day. GIBS paints
 * every value with a fixed colour, so the colour of each pixel is turned back
 * into its value (data/gibsColormaps.js), then painted again with our own scale,
 * narrowed to the range that matters here (GIBS colours 0–32 °C, which makes
 * the whole region one shade of red). The result is a texture on a thin piece of
 * sphere just above the Earth, so it moves with the globe.
 */

const WMS = "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"
const BBOX = { west: 90, east: 150, south: -15, north: 25 }
const IMG = { w: 1500, h: 1000 } // 0.04° per pixel
const RADIUS = 1.003 // just above the Earth (1) and under the clouds (1.005)
const D = Math.PI / 180

export const OCEAN_LAYERS = {
  sst: {
    title: "Sea temperature",
    gibs: "GHRSST_L4_MUR_Sea_Surface_Temperature",
    lut: SST,
    unit: "°C",
    min: 26,
    max: 32,
    ticks: [26, 28, 30, 32],
    ramp: ["#313695", "#4575b4", "#74add1", "#abd9e9", "#fee090", "#fdae61", "#f46d43", "#d73027", "#a50026"],
    source: "NASA MUR, daily",
  },
  salinity: {
    title: "Salinity",
    gibs: "SMAP_L3_Sea_Surface_Salinity_CAP_8Day_RunningMean",
    lut: SALINITY,
    unit: "PSU",
    min: 30,
    max: 35,
    ticks: [30, 31, 32, 33, 34, 35],
    ramp: ["#8c510a", "#d8b365", "#f6e8c3", "#c7eae5", "#5ab4ac", "#01665e"],
    source: "NASA SMAP, 8-day average, ~40 km so rough near coasts",
  },
  rain: {
    title: "Rainfall",
    gibs: "IMERG_Precipitation_Rate",
    lut: RAIN,
    unit: "mm/hr",
    min: 0.1,
    max: 20,
    log: true,
    ticks: [0.1, 1, 5, 20],
    ramp: ["#c6dbef", "#6baed6", "#2171b5", "#54278f", "#3f007d"],
    alpha: [0.45, 0.95], // light rain is faint so the sea still shows through
    source: "NASA GPM IMERG",
  },
}

const DAY = 86400000
const SHORT = new Intl.DateTimeFormat("en", { day: "numeric", month: "short" })
const isoDay = (d) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`

/** 0..1 position of a value on the layer's scale. */
function position(layer, v) {
  const t = layer.log
    ? (Math.log(v) - Math.log(layer.min)) / (Math.log(layer.max) - Math.log(layer.min))
    : (v - layer.min) / (layer.max - layer.min)
  return Math.min(1, Math.max(0, t))
}

/** 256 RGBA steps along the layer's colour ramp. */
function rampTable(layer) {
  const stops = layer.ramp.map((h) => new THREE.Color(h))
  const table = new Uint8ClampedArray(256 * 4)
  const [a0, a1] = layer.alpha || [1, 1]
  for (let i = 0; i < 256; i++) {
    const t = i / 255
    const f = t * (stops.length - 1)
    const k = Math.min(stops.length - 2, Math.floor(f))
    const c = stops[k].clone().lerp(stops[k + 1], f - k)
    table.set([c.r * 255, c.g * 255, c.b * 255, (a0 + (a1 - a0) * t) * 255], i * 4)
  }
  return table
}

function loadImage(url) {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.crossOrigin = "anonymous" // GIBS sends Access-Control-Allow-Origin: *
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error(`Could not load ${url}`))
    img.src = url
  })
}

/**
 * One day of one layer, recoloured. Resolves to a canvas, or null when GIBS has
 * nothing for that day (it then returns a fully transparent image).
 */
async function buildCanvas(layer, day) {
  const params = new URLSearchParams({
    SERVICE: "WMS",
    REQUEST: "GetMap",
    VERSION: "1.3.0",
    LAYERS: layer.gibs,
    STYLES: "",
    CRS: "EPSG:4326",
    BBOX: `${BBOX.south},${BBOX.west},${BBOX.north},${BBOX.east}`, // WMS 1.3 + EPSG:4326 = lat,lon order
    WIDTH: String(IMG.w),
    HEIGHT: String(IMG.h),
    FORMAT: "image/png",
    TRANSPARENT: "true",
    TIME: day,
  })
  const img = await loadImage(`${WMS}?${params}`)

  const canvas = document.createElement("canvas")
  canvas.width = IMG.w
  canvas.height = IMG.h
  const ctx = canvas.getContext("2d", { willReadFrequently: true })
  ctx.drawImage(img, 0, 0)
  const data = ctx.getImageData(0, 0, IMG.w, IMG.h)
  const px = data.data

  const values = layer.values || (layer.values = new Map(layer.lut))
  const table = layer.table || (layer.table = rampTable(layer))
  const EDGE = 60 // px (about 2.4°) over which the map fades out at its borders
  let painted = 0

  for (let y = 0, i = 0; y < IMG.h; y++) {
    for (let x = 0; x < IMG.w; x++, i += 4) {
      if (px[i + 3] < 128) {
        px[i + 3] = 0
        continue
      }
      const v = values.get((px[i] << 16) | (px[i + 1] << 8) | px[i + 2])
      if (v === undefined || (layer.log && v < layer.min)) {
        px[i + 3] = 0 // land, no data, or (rain) too light to show
        continue
      }
      const k = Math.round(position(layer, v) * 255) * 4
      const edge = Math.min(1, x / EDGE, y / EDGE, (IMG.w - 1 - x) / EDGE, (IMG.h - 1 - y) / EDGE)
      px[i] = table[k]
      px[i + 1] = table[k + 1]
      px[i + 2] = table[k + 2]
      px[i + 3] = table[k + 3] * edge
      painted++
    }
  }
  if (!painted) return null
  ctx.putImageData(data, 0, 0)
  return canvas
}

/**
 * @param {import("../earth/EarthGlobe.js").EarthGlobe} globe
 * @param {HTMLElement} legend  element the legend is drawn into
 * @returns {{show:(id:string|null)=>void, setDate:(d:Date)=>void}}
 */
export function mountOceanLayer(globe, legend) {
  const material = new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.88, depthWrite: false })
  const mesh = new THREE.Mesh(
    new THREE.SphereGeometry(
      RADIUS,
      128,
      96,
      (BBOX.west + 180) * D, // three.js phi = longitude + 180°
      (BBOX.east - BBOX.west) * D,
      (90 - BBOX.north) * D, // three.js theta = 90° − latitude
      (BBOX.north - BBOX.south) * D,
    ),
    material,
  )
  mesh.visible = false
  mesh.renderOrder = 1
  globe.ready.then(() => globe.scene.add(mesh))

  const cache = new Map() // "layer|day" → Promise<{canvas, day}|null>
  let active = null
  let date = new Date()
  let request = 0

  /** The selected day, or the newest day GIBS has, stepping back up to a week. */
  function fetchDay(id) {
    const layer = OCEAN_LAYERS[id]
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    // Satellite maps arrive a day or more late, and none exist for forecast days.
    const start = new Date(Math.min(date.getTime(), today.getTime() - DAY))
    const key = `${id}|${isoDay(start)}`
    if (!cache.has(key)) {
      const p = (async () => {
        for (let back = 0; back < 8; back++) {
          const d = new Date(start.getTime() - back * DAY)
          const canvas = await buildCanvas(layer, isoDay(d))
          if (canvas) return { canvas, day: d }
        }
        return null
      })()
      p.catch(() => cache.delete(key)) // let a later try load it again
      cache.set(key, p)
    }
    return cache.get(key)
  }

  async function update() {
    const id = active
    const n = ++request
    if (!id) {
      mesh.visible = false
      legend.hidden = true
      return
    }
    const layer = OCEAN_LAYERS[id]
    renderLegend(layer, { loading: true })
    try {
      const res = await fetchDay(id)
      if (n !== request) return // a newer choice won
      if (!res) {
        mesh.visible = false
        renderLegend(layer, { error: "No map for these days yet." })
        return
      }
      if (material.map) material.map.dispose()
      const tex = new THREE.CanvasTexture(res.canvas)
      tex.colorSpace = THREE.SRGBColorSpace
      tex.anisotropy = 4
      material.map = tex
      material.needsUpdate = true
      mesh.visible = true
      renderLegend(layer, { day: res.day })
    } catch (err) {
      if (n !== request) return
      console.error(err)
      mesh.visible = false
      renderLegend(layer, { error: "The map couldn’t load. Check your connection and try again." })
    }
  }

  function renderLegend(layer, { loading, error, day } = {}) {
    legend.hidden = false
    const gradient = layer.ramp.join(", ")
    const ticks = layer.ticks
      .map((t, i) => {
        const edge = i === 0 ? " first" : i === layer.ticks.length - 1 ? " last" : ""
        return `<span class="legend-tick${edge}" style="left:${(position(layer, t) * 100).toFixed(1)}%">${t}</span>`
      })
      .join("")
    const later = day && isoDay(day) < isoDay(date)
    const when = day
      ? `${later ? "Latest map" : "Map"}: ${SHORT.format(day)}${later && date > new Date() ? " (no forecast maps yet)" : ""}`
      : ""
    legend.innerHTML = `
      <div class="legend-head"><span class="legend-title">${layer.title}</span><span class="legend-unit">${layer.unit}</span></div>
      <div class="legend-bar" style="background:linear-gradient(90deg, ${gradient})"></div>
      <div class="legend-ticks" aria-hidden="true">${ticks}</div>
      <p class="legend-note">${loading ? "Loading map…" : error || `${when} · ${layer.source}`}</p>`
    legend.setAttribute(
      "aria-label",
      `${layer.title} colour scale from ${layer.ticks[0]} to ${layer.ticks.at(-1)} ${layer.unit}`,
    )
  }

  return {
    show(id) {
      active = id && OCEAN_LAYERS[id] ? id : null
      update()
    },
    setDate(d) {
      date = new Date(d)
      date.setHours(0, 0, 0, 0)
      if (active) update()
    },
  }
}
