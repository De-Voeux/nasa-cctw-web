// Pure coordinate math for the Earth globe. No three.js dependency, so it is
// testable under plain Node and reusable outside the renderer.
//
// World convention (matches THREE.SphereGeometry with an equirectangular map
// whose left edge is longitude -180°):
//   +Y  = north pole
//   +X  = (lat 0°, lon 0°)   Greenwich on the equator
//   -Z  = (lat 0°, lon 90°E)
//   +Z  = (lat 0°, lon 90°W)
// The Earth mesh is never rotated or tilted, so these formulas are time-invariant.
// Anything that spins (auto-rotate, user drag) moves the camera instead.

const DEG = Math.PI / 180

/** Wrap a longitude into [-180, 180). */
export function normalizeLon(lon) {
  return ((((lon + 180) % 360) + 360) % 360) - 180
}

/** Clamp a latitude into [-90, 90]. */
export function clampLat(lat) {
  return Math.max(-90, Math.min(90, lat))
}

/** @returns {{x:number,y:number,z:number}} point on a sphere of the given radius. */
export function latLonToXYZ(lat, lon, radius = 1) {
  const la = clampLat(lat) * DEG
  const lo = lon * DEG
  const c = Math.cos(la)
  return {
    x: radius * c * Math.cos(lo),
    y: radius * Math.sin(la),
    z: -radius * c * Math.sin(lo),
  }
}

/** Inverse of latLonToXYZ. The vector does not need to be unit length. */
export function xyzToLatLon(x, y, z) {
  const r = Math.hypot(x, y, z)
  if (r === 0) throw new RangeError("Cannot derive lat/lon from the zero vector")
  return {
    lat: Math.asin(Math.max(-1, Math.min(1, y / r))) / DEG,
    lon: normalizeLon(Math.atan2(-z, x) / DEG),
  }
}

/**
 * Altitude is measured in Earth radii above the surface, so the camera
 * distance from the Earth's centre is 1 + altitude when the radius is 1.
 */
export function altitudeToDistance(altitude, radius = 1) {
  return radius * (1 + altitude)
}

export function distanceToAltitude(distance, radius = 1) {
  return distance / radius - 1
}
