import test from "node:test"
import assert from "node:assert/strict"
import * as THREE from "three"
import {
  latLonToXYZ,
  xyzToLatLon,
  normalizeLon,
  altitudeToDistance,
  distanceToAltitude,
} from "./geo.mjs"

const near = (a, b, eps = 1e-9) =>
  assert.ok(Math.abs(a - b) < eps, `expected ${a} ≈ ${b}`)

test("cardinal points", () => {
  const g = latLonToXYZ(0, 0)
  near(g.x, 1); near(g.y, 0); near(g.z, 0)

  const east = latLonToXYZ(0, 90)
  near(east.x, 0); near(east.y, 0); near(east.z, -1)

  const west = latLonToXYZ(0, -90)
  near(west.x, 0); near(west.y, 0); near(west.z, 1)

  const north = latLonToXYZ(90, 0)
  near(north.x, 0); near(north.y, 1); near(north.z, 0)

  const south = latLonToXYZ(-90, 0)
  near(south.y, -1)
})

test("radius scales the result", () => {
  const p = latLonToXYZ(-6.2, 106.8, 10)
  near(Math.hypot(p.x, p.y, p.z), 10)
})

test("round trip, including Jakarta and the antimeridian", () => {
  const cases = [
    [-6.2, 106.8], [0, 0], [51.4769, 0], [40.7, -74], [-33.9, 151.2], [10, 179.5], [10, -179.5],
  ]
  for (const [lat, lon] of cases) {
    const p = latLonToXYZ(lat, lon, 3)
    const back = xyzToLatLon(p.x, p.y, p.z)
    near(back.lat, lat, 1e-9)
    near(back.lon, lon, 1e-9)
  }
})

test("poles map back to lat ±90 without NaN", () => {
  assert.equal(xyzToLatLon(0, 1, 0).lat, 90)
  assert.equal(xyzToLatLon(0, -1, 0).lat, -90)
  assert.ok(Number.isFinite(xyzToLatLon(0, 1, 0).lon))
})

test("zero vector is rejected", () => {
  assert.throws(() => xyzToLatLon(0, 0, 0), RangeError)
})

test("longitude normalisation", () => {
  assert.equal(normalizeLon(180), -180)
  assert.equal(normalizeLon(-180), -180)
  assert.equal(normalizeLon(190), -170)
  assert.equal(normalizeLon(-190), 170)
  assert.equal(normalizeLon(540), -180)
})

test("altitude <-> distance", () => {
  near(altitudeToDistance(0.5), 1.5)
  near(distanceToAltitude(altitudeToDistance(2.25, 6), 6), 2.25)
})

// The important one: the texture sits on THREE.SphereGeometry according to its
// own UV layout. If our lat/lon formula disagreed with that layout, every
// click-to-coordinate and fly-to would be wrong while still "looking" fine.
test("matches THREE.SphereGeometry UV layout for every vertex", () => {
  const geo = new THREE.SphereGeometry(1, 128, 64)
  const pos = geo.attributes.position
  const uv = geo.attributes.uv
  let worst = 0
  for (let i = 0; i < pos.count; i++) {
    const lon = uv.getX(i) * 360 - 180
    const lat = uv.getY(i) * 180 - 90
    const e = latLonToXYZ(lat, lon, 1)
    worst = Math.max(
      worst,
      Math.hypot(pos.getX(i) - e.x, pos.getY(i) - e.y, pos.getZ(i) - e.z),
    )
  }
  assert.ok(worst < 1e-5, `max vertex deviation ${worst}`)
})
