// GLSL for the Earth globe. Technique follows Franky Hung's "Make Your Own
// Earth in Three.js" (atmosphere rim shader, cloud-shadow "negative light map",
// ocean roughness inversion, night lights). Adapted for a world-fixed Earth
// and optional per-effect toggles.

export const atmosphereVertex = /* glsl */ `
varying vec3 vNormal;
varying vec3 eyeVector;

void main() {
  vec4 mvPos = modelViewMatrix * vec4( position, 1.0 );
  vNormal = normalize( normalMatrix * normal );
  // vector pointing from camera to vertex in view space
  eyeVector = normalize( mvPos.xyz );
  gl_Position = projectionMatrix * mvPos;
}
`

export const atmosphereFragment = /* glsl */ `
varying vec3 vNormal;
varying vec3 eyeVector;
uniform float atmOpacity;
uniform float atmPowFactor;
uniform float atmMultiplier;

void main() {
  // Back faces only: from the rim to the centre dotP rises from 0 to 1
  float dotP = dot( vNormal, eyeVector );
  float factor = pow( dotP, atmPowFactor ) * atmMultiplier;
  // whiten slightly as the glow intensifies
  vec3 atmColor = vec3( 0.35 + dotP / 4.5, 0.35 + dotP / 4.5, 1.0 );
  gl_FragColor = vec4( atmColor, atmOpacity ) * factor;
}
`

const NIGHT_LIGHTS_BLOCK = /* glsl */ `
#ifdef USE_EMISSIVEMAP
  vec4 emissiveColor = texture2D( emissiveMap, vEmissiveMapUv );
  // Show city lights only where the surface faces away from the sun.
  emissiveColor *= 1.0 - smoothstep( -0.02, 0.0, dot( geometryNormal, directionalLights[0].direction ) );
  totalEmissiveRadiance *= emissiveColor.rgb;
#endif
`

// Cloud shadow: for a ground point at uv X, sample the cloud texture at the uv
// of the cloud directly above it. The cloud sphere is rotated by `alpha`
// radians relative to the (fixed) ground, so the cloud above uv.x was painted
// at uv.x - alpha / (2*pi).
const cloudShadowBlock = (channel) => /* glsl */ `
  float cloudsMapValue = texture2D( tClouds, vec2( vMapUv.x - uv_xOffset, vMapUv.y ) ).${channel};
  diffuseColor.rgb *= max( 1.0 - cloudsMapValue, 0.2 );
`

const FRESNEL_BLOCK = /* glsl */ `
  // thin bluish haze toward the limb, in view space
  float fresnelIntensity = 1.4 - dot( geometryNormal, vec3( 0.0, 0.0, 1.0 ) );
  diffuseColor.rgb += vec3( 0.3, 0.6, 1.0 ) * pow( fresnelIntensity, 5.0 );
`

const OCEAN_ROUGHNESS_BLOCK = /* glsl */ `
float roughnessFactor = roughness;
#ifdef USE_ROUGHNESSMAP
  vec4 texelRoughness = texture2D( roughnessMap, vRoughnessMapUv );
  // the ocean map is white over water; roughness must be low there
  texelRoughness = vec4( 1.0 ) - texelRoughness;
  roughnessFactor *= clamp( texelRoughness.g, 0.5, 1.0 );
#endif
`

/**
 * Patch a MeshStandardMaterial in place.
 * @param {THREE.MeshStandardMaterial} material
 * @param {object} cfg
 * @param {{value:number}} cfg.uvXOffset shared uniform, updated every frame
 * @param {THREE.Texture|null} cfg.cloudsTexture sampled for cloud shadows
 * @param {"r"|"a"} cfg.cloudChannel texture channel that carries cloud density
 * @param {boolean} cfg.nightLights
 * @param {boolean} cfg.fresnel
 * @param {boolean} cfg.oceanRoughness
 */
export function patchEarthMaterial(material, cfg) {
  const { uvXOffset, cloudsTexture, cloudChannel, nightLights, fresnel, oceanRoughness } = cfg
  const useClouds = !!cloudsTexture

  // three.js keys its program cache on the onBeforeCompile source text, which is
  // identical for every globe. Without this, two globes with different effects
  // would silently share one compiled program.
  material.customProgramCacheKey = () =>
    `earth:${useClouds ? cloudChannel : "-"}:${nightLights ? 1 : 0}${fresnel ? 1 : 0}${oceanRoughness ? 1 : 0}`

  material.onBeforeCompile = (shader) => {
    if (useClouds) {
      shader.uniforms.tClouds = { value: cloudsTexture }
      shader.uniforms.uv_xOffset = uvXOffset
      shader.fragmentShader = shader.fragmentShader.replace(
        "#include <common>",
        `#include <common>\nuniform sampler2D tClouds;\nuniform float uv_xOffset;`,
      )
    }

    const emissive = [
      nightLights ? NIGHT_LIGHTS_BLOCK : "#include <emissivemap_fragment>",
      useClouds ? cloudShadowBlock(cloudChannel) : "",
      fresnel ? FRESNEL_BLOCK : "",
    ].join("\n")
    shader.fragmentShader = shader.fragmentShader.replace("#include <emissivemap_fragment>", emissive)

    if (oceanRoughness) {
      shader.fragmentShader = shader.fragmentShader.replace(
        "#include <roughnessmap_fragment>",
        OCEAN_ROUGHNESS_BLOCK,
      )
    }
  }
}
