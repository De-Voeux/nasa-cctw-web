import * as THREE from "three"
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js"
import { latLonToXYZ, xyzToLatLon, clampLat, altitudeToDistance, distanceToAltitude } from "./geo.mjs"
import { atmosphereVertex, atmosphereFragment, patchEarthMaterial, applyTerminatorSoftness } from "./shaders.js"

/**
 * @typedef {Object} EarthTextures  URLs (or any string TextureLoader accepts).
 * @property {string} albedo   required. Equirectangular, left edge = lon -180.
 * @property {string} [normal] normal map (use this OR `bump`)
 * @property {string} [bump]
 * @property {string} [ocean]  white over water, black over land
 * @property {string} [clouds] see `cloudsFormat`
 * @property {string} [lights] city lights, only used when effects.nightLights
 * @property {string} [sky]    background image, loaded after `ready`. A 2:1 image is wrapped
 *   around the viewer (equirectangular); any other ratio is a flat backdrop that covers
 *   the canvas at its original proportions, cropped evenly, never stretched.
 *
 * @typedef {Object} EarthGlobeOptions
 * @property {EarthTextures} textures
 * @property {"alpha"|"luminance"} [cloudsFormat="alpha"]  where the cloud texture stores density:
 *   its alpha channel, or its brightness (NASA Blue Marble clouds).
 * @property {{lat:number,lon:number,altitude:number}} [initialView]
 * @property {number} [minAltitude=0.15]  Earth radii above the surface
 * @property {number} [maxAltitude=8]
 * @property {boolean|{enabled?:boolean,speed?:number,resumeAfterMs?:number|null}} [autoRotate]
 *   on by default. Stops on any user interaction, then resumes after
 *   `resumeAfterMs` (default 5000; null = never resume).
 * @property {{clouds?:boolean,atmosphere?:boolean,nightLights?:boolean,oceanReflection?:boolean}} [effects]
 * @property {"camera"|"fixed"} [lighting="camera"]  the sun is a directional light.
 *   "camera" holds it at a fixed angle from the viewing direction, so the globe always
 *   shows a day side and a night side like the article's demo, however the user rotates.
 *   "fixed" pins it in world space at `sunDirection`.
 * @property {number} [sunAzimuth=-59]  degrees off the viewing axis, negative = left ("camera" mode)
 * @property {number} [sunElevation=0]  degrees above the viewing axis ("camera" mode)
 * @property {[number,number,number]} [sunDirection]  world direction toward the sun ("fixed" mode)
 * @property {number} [ambient=0]  ambient light; 0 leaves the night side black, as in the article
 * @property {number} [nightLightsIntensity=3]  brightness of the city lights (see DEFAULTS)
 * @property {number} [terminatorSoftness=0.3]  width of the dusk band between day and night
 *   (wrap lighting); 0 gives a hard edge
 * @property {string|number|null} [background="#02040a"]  null = transparent canvas
 * @property {number} [maxPixelRatio=2]
 * @property {"auto"|"low"|"high"} [quality="auto"]
 */

const DEFAULTS = {
  cloudsFormat: "alpha",
  initialView: { lat: 0, lon: 110, altitude: 3 },
  minAltitude: 0.15,
  maxAltitude: 8,
  autoRotate: { enabled: true, speed: 0.5, resumeAfterMs: 5000 },
  effects: { clouds: true, atmosphere: true, nightLights: true, oceanReflection: true },
  lighting: "camera",
  // The article puts the sun at (-50, 0, 30) for a camera at (0, 0, 30): 59° to the
  // left of the viewing axis, level with the camera.
  sunAzimuth: -59,
  sunElevation: 0,
  sunDirection: [-1, 0.2, 0.6],
  ambient: 0,
  // The article's city-lights map is 16384x8192. We ship it at 4096x2048, which blurs the
  // small points of light and dims them, so they are boosted to look similar. Use 1 with
  // the full-size map.
  nightLightsIntensity: 3,
  // 0 = hard terminator (stock three.js). Around 0.3 gives a twilight band like the
  // atmosphere makes on the real Earth; light then fades out gradually past the terminator.
  terminatorSoftness: 0.3,
  background: "#02040a",
  maxPixelRatio: 2,
  quality: "auto",
}

// Vertical field of view (degrees) in landscape containers.
const BASE_FOV = 45
// Same sun strength as the article's demo.
const SUN_INTENSITY = 1.8
// Relative cloud drift over the ground, radians per second.
const CLOUD_DRIFT = 0.01
// The article uses bumpScale 0.03 on a sphere of radius 10. three.js evaluates
// bump in object-space units, so the equivalent for our radius-1 sphere is 0.003.
const BUMP_SCALE = 0.003
// Atmosphere shell radius / cloud shell radius, in Earth radii.
const ATMOS_RADIUS = 1.25
const CLOUD_RADIUS = 1.005
const ATMOS_BASE = { opacity: 0.7, pow: 4.1, mult: 9.5 }

function normalizeOptions(o) {
  const ar = o.autoRotate
  const autoRotate =
    typeof ar === "boolean"
      ? { ...DEFAULTS.autoRotate, enabled: ar }
      : { ...DEFAULTS.autoRotate, ...(ar || {}) }
  return {
    ...DEFAULTS,
    ...o,
    initialView: { ...DEFAULTS.initialView, ...(o.initialView || {}) },
    autoRotate,
    effects: { ...DEFAULTS.effects, ...(o.effects || {}) },
  }
}

const easeInOutCubic = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2)

export class EarthGlobe {
  /**
   * @param {HTMLElement} container must have a non-zero size from CSS
   * @param {EarthGlobeOptions} options
   */
  constructor(container, options) {
    if (!container) throw new Error("EarthGlobe: container element is required")
    if (!options || !options.textures || !options.textures.albedo) {
      throw new Error("EarthGlobe: options.textures.albedo is required")
    }
    this.container = container
    this.opts = normalizeOptions(options)

    this._listeners = new Map()
    this._disposed = false
    this._textures = []
    this._raf = 0
    this._lastT = 0
    this._cloudAngle = 0
    this._uvXOffset = { value: 0 }
    this._atmos = null
    this._clouds = null
    this._earth = null
    this._flight = null
    this._resumeTimer = null

    const mq = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : null
    this._reducedMotion = !!(mq && mq.matches)
    this._autoRotateWanted = this.opts.autoRotate.enabled

    this._initRenderer()
    this._initScene()
    this._initControls()
    this._initPicking()
    this._initResize()

    this.setView(this.opts.initialView)

    this.ready = this._loadAndBuild().then(
      () => {
        this._emit("ready")
        return this
      },
      (err) => {
        this._emit("error", err)
        throw err
      },
    )
    // Avoid an "unhandled rejection" when the caller only listens to events.
    this.ready.catch(() => {})

    this._raf = requestAnimationFrame((t) => this._tick(t))
  }

  // ---------------------------------------------------------------- events

  /** @param {"ready"|"error"|"viewchange"|"select"|"frame"} type  "frame" fires after every render */
  on(type, fn) {
    if (!this._listeners.has(type)) this._listeners.set(type, new Set())
    this._listeners.get(type).add(fn)
    return () => this.off(type, fn)
  }

  off(type, fn) {
    const set = this._listeners.get(type)
    if (set) set.delete(fn)
  }

  _emit(type, payload) {
    const set = this._listeners.get(type)
    if (!set) return
    for (const fn of [...set]) fn(payload)
  }

  // ------------------------------------------------------------- public API

  /** Current camera-centre point and distance. Altitude is in Earth radii. */
  getView() {
    const p = this.camera.position
    const { lat, lon } = xyzToLatLon(p.x, p.y, p.z)
    return { lat, lon, altitude: distanceToAltitude(p.length()) }
  }

  /** Jump instantly. Omitted fields keep their current value. */
  setView(view) {
    this._cancelFlight(false)
    const cur = this._safeCurrentView()
    const lat = clampLat(view.lat ?? cur.lat)
    const lon = view.lon ?? cur.lon
    const altitude = THREE.MathUtils.clamp(view.altitude ?? cur.altitude, this.opts.minAltitude, this.opts.maxAltitude)
    // keep off the exact poles: OrbitControls loses its azimuth there
    const p = latLonToXYZ(THREE.MathUtils.clamp(lat, -89.5, 89.5), lon, altitudeToDistance(altitude))
    this.camera.position.set(p.x, p.y, p.z)
    this.camera.lookAt(0, 0, 0)
    this.controls.update()
  }

  /**
   * Animate along the great circle to the target. Stops auto-rotate.
   * @returns {Promise<boolean>} true if it arrived, false if superseded or disposed
   */
  flyTo({ lat, lon, altitude, duration = 2000 }) {
    this._cancelFlight(false)
    this.setAutoRotate(false)

    const from = this.camera.position.clone()
    const fromDir = from.clone().normalize()
    const t = latLonToXYZ(THREE.MathUtils.clamp(lat, -89.5, 89.5), lon, 1)
    const toDir = new THREE.Vector3(t.x, t.y, t.z)
    const fromDist = from.length()
    const toDist = altitudeToDistance(
      THREE.MathUtils.clamp(altitude ?? distanceToAltitude(fromDist), this.opts.minAltitude, this.opts.maxAltitude),
    )
    const q = new THREE.Quaternion().setFromUnitVectors(fromDir, toDir)
    const qId = new THREE.Quaternion()

    return new Promise((resolve) => {
      this._flight = {
        start: performance.now(),
        duration: Math.max(1, duration),
        resolve,
        step: (k) => {
          const e = easeInOutCubic(k)
          const dir = fromDir.clone().applyQuaternion(qId.clone().slerp(q, e))
          const dist = fromDist + (toDist - fromDist) * e
          this.camera.position.copy(dir.multiplyScalar(dist))
          this.camera.lookAt(0, 0, 0)
        },
      }
      this.controls.enabled = false
    })
  }

  /**
   * Where a surface point appears on screen, in viewport (client) pixels.
   * `facing` is the cosine between the surface normal and the direction to the
   * camera: 1 = straight on, 0 = on the visible horizon, < 0 = far side.
   * Pass `rect` (the canvas getBoundingClientRect) when projecting many points
   * per frame, and `out` to avoid allocating.
   * @returns {{x:number, y:number, facing:number, visible:boolean}}
   */
  project(lat, lon, rect = this.renderer.domElement.getBoundingClientRect(), out = {}) {
    const p = latLonToXYZ(lat, lon, 1)
    const v = this._projVec || (this._projVec = new THREE.Vector3())
    v.set(p.x, p.y, p.z)
    const c = this.camera.position
    const dx = c.x - v.x
    const dy = c.y - v.y
    const dz = c.z - v.z
    // v is a unit vector, so this is the cosine between normal and view ray.
    const facing = (v.x * dx + v.y * dy + v.z * dz) / (Math.hypot(dx, dy, dz) || 1)
    v.project(this.camera)
    out.x = rect.left + ((v.x + 1) / 2) * rect.width
    out.y = rect.top + ((1 - v.y) / 2) * rect.height
    out.facing = facing
    out.visible = facing > 0
    return out
  }

  /** Enable/disable the idle spin. Respects prefers-reduced-motion. */
  setAutoRotate(enabled) {
    this._autoRotateWanted = !!enabled
    this._clearResume()
    this.controls.autoRotate = this._autoRotateWanted && !this._reducedMotion
  }

  resize() {
    const w = Math.max(1, this.container.clientWidth)
    const h = Math.max(1, this.container.clientHeight)
    this.renderer.setSize(w, h, false)
    const aspect = w / h
    this.camera.aspect = aspect
    // Portrait containers (phones): keep the horizontal field of view fixed
    // so the globe is not cropped at the sides.
    const base = THREE.MathUtils.degToRad(BASE_FOV)
    this.camera.fov = aspect < 1 ? THREE.MathUtils.radToDeg(2 * Math.atan(Math.tan(base / 2) / aspect)) : BASE_FOV
    this.camera.updateProjectionMatrix()
    this._fitSky()
  }

  /** Release GPU resources and listeners. Safe to call twice. */
  dispose() {
    if (this._disposed) return
    this._disposed = true
    cancelAnimationFrame(this._raf)
    this._cancelFlight(false)
    this._clearResume()
    this._ro && this._ro.disconnect()
    const el = this.renderer.domElement
    el.removeEventListener("pointerdown", this._onDown)
    el.removeEventListener("pointerup", this._onUp)
    this.controls.dispose()
    this.scene.traverse((o) => {
      if (o.geometry) o.geometry.dispose()
      if (o.material) {
        for (const m of Array.isArray(o.material) ? o.material : [o.material]) m.dispose()
      }
    })
    for (const t of this._textures) t.dispose()
    this._textures.length = 0
    this.renderer.dispose()
    this.renderer.forceContextLoss()
    el.remove()
    this._listeners.clear()
  }

  // ---------------------------------------------------------------- setup

  _initRenderer() {
    const transparent = this.opts.background === null
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: transparent })
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, this.opts.maxPixelRatio))
    this.renderer.outputColorSpace = THREE.SRGBColorSpace
    const el = this.renderer.domElement
    el.style.cssText = "display:block;width:100%;height:100%;outline:none"
    this.container.appendChild(el)
  }

  _initScene() {
    this.scene = new THREE.Scene()
    if (this.opts.background !== null) this.scene.background = new THREE.Color(this.opts.background)

    this.camera = new THREE.PerspectiveCamera(BASE_FOV, 1, 0.01, 100)

    // The sun is a directional light aimed at the Earth's centre.
    this._sun = new THREE.DirectionalLight(0xffffff, SUN_INTENSITY)
    this.scene.add(this._sun)
    const az = THREE.MathUtils.degToRad(this.opts.sunAzimuth)
    const el = THREE.MathUtils.degToRad(this.opts.sunElevation)
    // Unit vector toward the sun in camera-aligned axes centred on the Earth, where
    // +z points from the Earth toward the camera. With azimuth -59° and elevation 0 this
    // is the article's light direction, whatever the camera distance.
    this._sunLocal = new THREE.Vector3(Math.sin(az) * Math.cos(el), Math.sin(el), Math.cos(az) * Math.cos(el))
    this._sunFixed = new THREE.Vector3(...this.opts.sunDirection).normalize()
    this._sunTmp = new THREE.Vector3()
    this._updateSun()
    if (this.opts.ambient > 0) this.scene.add(new THREE.AmbientLight(0xffffff, this.opts.ambient))
    this.resize()
  }

  /** Re-aim the sun. In "camera" mode it follows the camera's orientation. */
  _updateSun() {
    const dir =
      this.opts.lighting === "fixed"
        ? this._sunFixed
        : this._sunTmp.copy(this._sunLocal).applyQuaternion(this.camera.quaternion)
    this._sun.position.copy(dir).multiplyScalar(10)
  }

  _initControls() {
    const c = new OrbitControls(this.camera, this.renderer.domElement)
    c.enablePan = false
    c.enableDamping = true
    c.minDistance = altitudeToDistance(this.opts.minAltitude)
    c.maxDistance = altitudeToDistance(this.opts.maxAltitude)
    c.autoRotateSpeed = this.opts.autoRotate.speed
    this.controls = c

    c.addEventListener("start", () => {
      this._clearResume()
      c.autoRotate = false
    })
    c.addEventListener("end", () => {
      const ms = this.opts.autoRotate.resumeAfterMs
      if (!this._autoRotateWanted || ms == null || this._reducedMotion) return
      this._resumeTimer = setTimeout(() => {
        if (!this._disposed && this._autoRotateWanted) c.autoRotate = true
      }, ms)
    })
    c.addEventListener("change", () => this._emit("viewchange", this.getView()))

    c.autoRotate = this._autoRotateWanted && !this._reducedMotion
  }

  _initPicking() {
    const ray = new THREE.Raycaster()
    const ndc = new THREE.Vector2()
    let down = null
    this._onDown = (e) => {
      down = { x: e.clientX, y: e.clientY, t: performance.now() }
    }
    this._onUp = (e) => {
      if (!down || !this._earth) return
      const moved = Math.hypot(e.clientX - down.x, e.clientY - down.y)
      const quick = performance.now() - down.t < 500
      down = null
      if (moved > 5 || !quick) return // a drag, not a click
      const r = this.renderer.domElement.getBoundingClientRect()
      ndc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1)
      ray.setFromCamera(ndc, this.camera)
      const hit = ray.intersectObject(this._earth, false)[0]
      if (!hit) return
      // The Earth mesh is never rotated, so world space == globe space.
      const { lat, lon } = xyzToLatLon(hit.point.x, hit.point.y, hit.point.z)
      this._emit("select", { lat, lon })
    }
    this.renderer.domElement.addEventListener("pointerdown", this._onDown)
    this.renderer.domElement.addEventListener("pointerup", this._onUp)
  }

  _initResize() {
    if (typeof ResizeObserver === "undefined") return
    this._ro = new ResizeObserver(() => this.resize())
    this._ro.observe(this.container)
  }

  // ---------------------------------------------------------- build / loop

  _loadTexture(url, { srgb = false, repeatX = false } = {}) {
    return new Promise((resolve, reject) => {
      new THREE.TextureLoader().load(
        url,
        (tex) => {
          if (this._disposed) return tex.dispose()
          if (srgb) tex.colorSpace = THREE.SRGBColorSpace
          if (repeatX) tex.wrapS = THREE.RepeatWrapping
          tex.anisotropy = Math.min(8, this.renderer.capabilities.getMaxAnisotropy())
          this._textures.push(tex)
          resolve(tex)
        },
        undefined,
        () => reject(new Error(`EarthGlobe: failed to load texture ${url}`)),
      )
    })
  }

  async _loadAndBuild() {
    const t = this.opts.textures
    const fx = this.opts.effects
    const wantClouds = fx.clouds && !!t.clouds
    const wantLights = fx.nightLights && !!t.lights
    const wantOcean = fx.oceanReflection && !!t.ocean
    const cloudsAsAlpha = this.opts.cloudsFormat === "alpha"

    const [albedo, normal, bump, ocean, clouds, lights] = await Promise.all([
      this._loadTexture(t.albedo, { srgb: true }),
      t.normal ? this._loadTexture(t.normal) : null,
      !t.normal && t.bump ? this._loadTexture(t.bump) : null,
      wantOcean ? this._loadTexture(t.ocean) : null,
      wantClouds ? this._loadTexture(t.clouds, { srgb: cloudsAsAlpha, repeatX: true }) : null,
      wantLights ? this._loadTexture(t.lights, { srgb: true }) : null,
    ])
    if (this._disposed) return

    const q = this.opts.quality
    const coarse = q === "low" || (q === "auto" && window.matchMedia && window.matchMedia("(pointer: coarse)").matches)
    const seg = coarse ? 48 : 96

    // --- Earth
    const earthMat = new THREE.MeshStandardMaterial({
      map: albedo,
      normalMap: normal || null,
      bumpMap: bump || null,
      bumpScale: BUMP_SCALE,
      roughness: 1,
      metalness: ocean ? 0.1 : 0,
      roughnessMap: ocean || null,
      metalnessMap: ocean || null,
      emissiveMap: lights || null,
      emissive: lights ? new THREE.Color(0xffff88) : new THREE.Color(0x000000),
      emissiveIntensity: this.opts.nightLightsIntensity,
    })
    patchEarthMaterial(earthMat, {
      uvXOffset: this._uvXOffset,
      cloudsTexture: clouds,
      cloudChannel: cloudsAsAlpha ? "a" : "r",
      nightLights: !!lights,
      fresnel: fx.atmosphere,
      oceanRoughness: !!ocean,
      terminatorSoftness: this.opts.terminatorSoftness,
    })
    this._earth = new THREE.Mesh(new THREE.SphereGeometry(1, seg, seg), earthMat)
    this.scene.add(this._earth)

    // --- Clouds (separate shell so they can drift and cast shadows)
    if (clouds) {
      const cloudMat = new THREE.MeshStandardMaterial(
        cloudsAsAlpha
          ? { map: clouds, transparent: true, depthWrite: false }
          : { alphaMap: clouds, transparent: true, depthWrite: false },
      )
      // Same soft terminator as the ground, or the clouds would vanish before the land does.
      applyTerminatorSoftness(cloudMat, this.opts.terminatorSoftness)
      this._clouds = new THREE.Mesh(new THREE.SphereGeometry(CLOUD_RADIUS, seg, seg), cloudMat)
      this.scene.add(this._clouds)
    }

    // --- Atmosphere rim glow
    if (fx.atmosphere) {
      this._atmosUniforms = {
        atmOpacity: { value: ATMOS_BASE.opacity },
        atmPowFactor: { value: ATMOS_BASE.pow },
        atmMultiplier: { value: ATMOS_BASE.mult },
      }
      const mat = new THREE.ShaderMaterial({
        vertexShader: atmosphereVertex,
        fragmentShader: atmosphereFragment,
        uniforms: this._atmosUniforms,
        blending: THREE.AdditiveBlending,
        side: THREE.BackSide,
        transparent: true,
        depthWrite: false,
      })
      this._atmos = new THREE.Mesh(new THREE.SphereGeometry(ATMOS_RADIUS, seg, seg), mat)
      this.scene.add(this._atmos)
    }

    if (t.sky) this._loadSky(t.sky)
  }

  /** Load the background without delaying `ready`; a failure is only reported via "error". */
  _loadSky(url) {
    this._loadTexture(url, { srgb: true }).then(
      (sky) => {
        if (this._disposed) return
        const ratio = sky.image.width / sky.image.height
        if (Math.abs(ratio - 2) < 0.05) {
          // 2:1 is an equirectangular map: wrap it around the viewer.
          sky.mapping = THREE.EquirectangularReflectionMapping
          this._skyAspect = null
        } else {
          // Any other ratio is a flat backdrop that keeps its own proportions (see _fitSky).
          sky.generateMipmaps = false
          sky.minFilter = THREE.LinearFilter
          this._skyAspect = ratio
        }
        this.scene.background = sky
        this._fitSky()
      },
      (err) => this._emit("error", err),
    )
  }

  /** "Cover" fit for a flat backdrop: fill the canvas, crop the overflow evenly, never stretch. */
  _fitSky() {
    const bg = this.scene.background
    if (!this._skyAspect || !bg || !bg.isTexture) return
    const f = this._skyAspect / this.camera.aspect
    bg.repeat.set(f > 1 ? 1 / f : 1, f > 1 ? 1 : f)
    bg.offset.set(f > 1 ? (1 - 1 / f) / 2 : 0, f > 1 ? 0 : (1 - f) / 2)
  }

  _safeCurrentView() {
    return this.camera.position.lengthSq() > 0
      ? this.getView()
      : { ...this.opts.initialView }
  }

  _clearResume() {
    if (this._resumeTimer) clearTimeout(this._resumeTimer)
    this._resumeTimer = null
  }

  _cancelFlight(arrived) {
    if (!this._flight) return
    const f = this._flight
    this._flight = null
    this.controls.enabled = true
    f.resolve(arrived)
  }

  _tick(now) {
    if (this._disposed) return
    this._raf = requestAnimationFrame((t) => this._tick(t))
    const dt = this._lastT ? Math.min(0.1, (now - this._lastT) / 1000) : 0
    this._lastT = now

    if (this._flight) {
      const k = Math.min(1, (performance.now() - this._flight.start) / this._flight.duration)
      this._flight.step(k)
      if (k >= 1) this._cancelFlight(true)
    }

    this.controls.update()
    const altitude = distanceToAltitude(this.camera.position.length())

    // Orbit controls feel too fast up close; scale drag speed with height.
    this.controls.rotateSpeed = THREE.MathUtils.clamp(altitude * 0.8, 0.1, 1)
    this.controls.zoomSpeed = THREE.MathUtils.clamp(altitude * 0.8, 0.3, 1)

    if (this._clouds && !this._reducedMotion) {
      this._cloudAngle += CLOUD_DRIFT * dt
      this._clouds.rotation.y = this._cloudAngle
      this._uvXOffset.value = (this._cloudAngle / (2 * Math.PI)) % 1
    }

    // The atmosphere shell is a back-face sphere of radius 1.25. Once the camera
    // is inside it, it would tint the whole screen, so fade it out on approach.
    if (this._atmos) {
      const k = THREE.MathUtils.smoothstep(altitude, 0.25, 0.9)
      this._atmos.visible = k > 0.001
      this._atmosUniforms.atmOpacity.value = ATMOS_BASE.opacity * k
    }

    this._updateSun()
    this.renderer.render(this.scene, this.camera)
    // After render, so HTML overlays positioned here match the drawn frame.
    this._emit("frame")
  }
}
