import {
  Color,
  Group,
  InstancedBufferAttribute,
  InstancedBufferGeometry,
  Mesh,
  OctahedronGeometry,
  PerspectiveCamera,
  Scene,
  ShaderMaterial,
  TorusGeometry,
  WebGLRenderer,
} from "three"
import type { InterviewerPose } from "../../interviewer/types"

/**
 * The InterMind interviewer, as an imperative three.js scene.
 *
 * Deliberately not a react-three-fiber scene graph: this is two instanced meshes with two
 * custom materials, so the reconciler bridge would add a dependency (and, on React 19.3, a peer
 * conflict) to manage two objects. React owns *what state* the interviewer is in; this module
 * owns how that state looks and eases.
 *
 * ## The form
 *
 * A gyroscopic cage: thin rings carried on crossing axes around a suspended nucleus of shards.
 * Not a character, not an orb, not a stack. The reference is a measuring instrument: an orrery
 * or a gyroscope, where meaning lives in how the axes are arranged relative to each other.
 * Perception is the cage opening outward; analysis is the axes tumbling out of agreement;
 * synthesis is the moment every axis falls into an even, deliberate distribution at once.
 *
 * The silhouette is asymmetric by construction. Each ring's inclination and radius carry a
 * per-ring random weighted by `order`, so at rest the cage is slightly irregular and hand-made
 * rather than machined, and only becomes exact at the one moment that means something.
 *
 * ## State as configuration, not speed
 *
 *   idle       half open, slow turn, nucleus loosely held
 *   listening  blades open wide and pitch face-on, presenting outward
 *   speaking   a wave runs around the ring on the real speech envelope
 *   thinking   blades close in, nucleus disperses and churns, armature turns fast
 *   evidence   exact lattice, nucleus condensed to one bright core, a sweep around the ring
 *   followUp   the ring collapses into a narrow fan pointed one way
 *
 * Because these are different shapes rather than different tempos, the reduced-motion path can
 * drop continuous animation entirely and still carry all six meanings.
 */

/* Shared helpers, injected into both vertex shaders. */
const GLSL_ROT = /* glsl */ `
mat2 rot(float a) {
  float c = cos(a);
  float s = sin(a);
  return mat2(c, -s, s, c);
}
`

const BLADE_VERTEX = /* glsl */ `
${GLSL_ROT}

uniform float uTime;
uniform float uOpen;
uniform float uTilt;
uniform float uOrder;
uniform float uFocus;
uniform float uWave;
uniform float uSpin;

attribute float aI;    // 0..1, this ring's place in the set
attribute float aR;    // per-ring random, 0..1

varying float vI;
varying float vFace;
varying float vDepth;
varying vec3 vNormal;
varying vec3 vView;

void main() {
  float ragged = 1.0 - uOrder;

  // Each ring is a full circle carried on its own axis. Where those axes point is the whole
  // design: evenly distributed when the instrument has resolved something, scattered while it
  // is still working. Crossing inclinations, never a coaxial stack.
  float thetaReg = (aI - 0.5) * 3.14159;
  float thetaRaw = thetaReg + (aR - 0.5) * 1.8;
  float phiReg = aI * 6.28318 * 2.0;
  float phiRaw = aI * 39.6 + aR * 12.0;

  float theta = mix(thetaRaw, thetaReg, uOrder) * (uTilt / 1.3);
  float phi = mix(phiRaw, phiReg, uOrder);

  // Precession. Every axis drifts at its own rate, which is what makes the cage read as a
  // running instrument rather than a static wireframe.
  phi += uTime * uSpin * (0.6 + aR * 1.2);
  theta += sin(uTime * (0.3 + uSpin) + aR * 8.0) * 0.22 * ragged;

  // Focus draws every axis toward a single heading, turning the cage into a directed cone.
  theta = mix(theta, 1.1, uFocus * 0.82);
  phi = mix(phi, 0.5, uFocus * 0.82);

  // Radius. The travelling term is the speech wave running through the set.
  float phase = aI * 6.28318 * 2.0 - uTime * 2.4;
  float radius = 0.52 + uOpen * 0.4 + aR * 0.1 * ragged + sin(phase) * uWave * 0.17;

  vec3 p = position * radius;
  // Each ring is an ellipse of its own eccentricity, and the set never resolves to concentric
  // circles. This is what keeps the silhouette sculptural instead of spherical.
  p.x *= 1.0 + aR * 0.34;
  p.z *= 1.0 - aR * 0.2;
  p.yz = rot(theta) * p.yz;
  p.xz = rot(phi) * p.xz;

  vec3 n = normal;
  n.yz = rot(theta) * n.yz;
  n.xz = rot(phi) * n.xz;

  vec4 mv = modelViewMatrix * vec4(p, 1.0);

  vI = aI;
  vDepth = -mv.z;
  vFace = 0.55 + 0.45 * abs(cos(theta));
  vNormal = normalize(normalMatrix * n);
  vView = normalize(-mv.xyz);
  gl_Position = projectionMatrix * mv;
}
`

const BLADE_FRAGMENT = /* glsl */ `
uniform float uCharge;
uniform float uOrder;
uniform float uSweep;
uniform float uSweepEnergy;
uniform vec3 uInk;
uniform vec3 uAccent;
uniform vec3 uHighlight;

varying float vI;
varying float vFace;
varying float vDepth;
varying vec3 vNormal;
varying vec3 vView;

void main() {
  vec3 n = normalize(vNormal);
  float fres = pow(1.0 - clamp(abs(dot(n, normalize(vView))), 0.0, 1.0), 2.4);

  // Indigo is the accent and pale sky the highlight inside it; the rings themselves stay
  // near-black. Letting the key light decide where colour lands is what keeps the instrument from
  // flattening into one tinted mass.
  vec3 accent = mix(uAccent, uHighlight, clamp(uCharge * 0.42, 0.0, 1.0));

  float key = max(dot(n, normalize(vec3(0.45, 0.72, 0.55))), 0.0);

  // The resolve sweep: one bright pass around the ring when evidence lands.
  float d = abs(fract(vI - uSweep + 0.5) - 0.5);
  float band = smoothstep(0.12, 0.0, d) * uSweepEnergy;

  vec3 col = mix(uInk, accent, (0.04 + uCharge * 0.1) + key * (0.2 + uCharge * 0.34));
  col += accent * fres * (0.18 + uCharge * 0.3);
  col += accent * band * 1.8;
  // Resolved blades pick up a cool edge, so the ordered state looks deliberate rather than
  // merely brighter.
  col += vec3(0.1, 0.09, 0.14) * uOrder * key * 0.5;

  float alpha = clamp(0.3 + vFace * 0.34 + key * 0.22 + band * 0.55 + uCharge * 0.05, 0.0, 0.95);
  // Rings on the far side recede, which is what separates a dimensional cage from a flat
  // tangle of overlapping outlines.
  alpha *= mix(0.28, 1.0, smoothstep(4.4, 2.2, vDepth));

  gl_FragColor = vec4(col, alpha);
}
`

const CORE_VERTEX = /* glsl */ `
${GLSL_ROT}

uniform float uTime;
uniform float uScatter;
uniform float uOrder;
uniform float uSpin;

attribute vec3 aSeed;  // unit direction on the sphere
attribute float aR;

varying float vR;
varying vec3 vNormal;

void main() {
  vec3 dir = normalize(aSeed);

  // Dispersion. At rest the shards hold a loose cloud; thinking throws them outward; evidence
  // condenses them to a single dense point, which is the visual of a conclusion forming.
  float radius = 0.05 + uScatter * 0.2 + sin(uTime * 0.9 + aR * 28.0) * uScatter * 0.035;
  // Deliberately off-centre: a nucleus sitting exactly in the middle reads as a decorative
  // bead, while an offset one reads as a suspended working part.
  vec3 centre = dir * radius + vec3(0.07, 0.05, -0.03);

  // The nucleus counter-rotates against the blades, on its own per-shard clock.
  centre.xz = rot(-uTime * (uSpin * 2.2) * (0.5 + aR)) * centre.xz;
  centre.xy = rot(uTime * uSpin * 0.7) * centre.xy;

  // Shards grow as they converge, so the condensed state reads as one solid core.
  float size = 0.008 + 0.018 * uOrder + (1.0 - uScatter) * 0.016;
  vec3 p = position * size + centre;

  vR = aR;
  vNormal = normalize(normalMatrix * normal);
  gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
}
`

const CORE_FRAGMENT = /* glsl */ `
uniform float uCharge;
uniform float uOrder;
uniform vec3 uAccent;
uniform vec3 uHighlight;
uniform vec3 uInk;

varying float vR;
varying vec3 vNormal;

void main() {
  vec3 n = normalize(vNormal);
  float key = max(dot(n, normalize(vec3(0.3, 0.8, 0.5))), 0.0);

  // The core is the one genuinely emissive element in the instrument, and even here it is
  // held back: indigo lifting toward pale sky as the system becomes certain.
  vec3 col = mix(uInk, uAccent, 0.55 + uCharge * 0.4);
  col = mix(col, uHighlight, uOrder * uCharge * 0.5);
  col += uAccent * key * 0.5;

  float alpha = clamp(0.5 + uCharge * 0.35 + uOrder * 0.15 + key * 0.2, 0.0, 1.0);
  gl_FragColor = vec4(col, alpha);
}
`

/** Which surface the instrument is being drawn on. */
export type InterviewerTone = "onLight" | "onDark"

/**
 * The instrument keeps one form and one set of states on both surfaces; only where the light
 * falls changes. On white, the rings are near-black filaments with indigo picking out the lit
 * edges. In the interview room the body of a ring would simply disappear into the background,
 * so the body itself carries a low indigo glow and pale sky becomes the highlight - the same
 * object, lit from the front rather than read as a silhouette.
 */
const TONE_PALETTE: Record<InterviewerTone, { ink: string; accent: string; highlight: string }> = {
  onLight: { ink: "#000505", accent: "#3b3355", highlight: "#bfcde0" },
  onDark: { ink: "#2f2d4d", accent: "#97a0c8", highlight: "#e9f1fc" },
}

export interface ProcessSceneHandle {
  ready: Promise<void>
  draw: (pose: InterviewerPose, progress: number) => boolean
  dispose: () => void
}

/**
 * Returns `null` when WebGL isn't available - callers render a static fallback rather than an
 * empty hole. Never throws: a missing interviewer must not take the interview down with it.
 */
export function createProcessScene(
  canvas: HTMLCanvasElement,
  
): ProcessSceneHandle | null {
  // Complexity follows rendered size. The instrument appears anywhere from ~150px on a phone
  // to ~560px in the hero, and a phone mid-interview should not pay hero cost.
  const cssSize = Math.max(canvas.clientWidth, canvas.clientHeight) || 220
  const BLADES = cssSize >= 420 ? 26 : cssSize >= 260 ? 18 : 12
  const TUBULAR = cssSize >= 420 ? 128 : 88
  const SHARDS = cssSize >= 420 ? 90 : cssSize >= 260 ? 64 : 40

  let renderer: WebGLRenderer
  try {
    renderer = new WebGLRenderer({
      canvas,
      alpha: true,
      antialias: true,
      powerPreference: "high-performance",
    })
  } catch {
    return null
  }

  const scene = new Scene()
  const camera = new PerspectiveCamera(40, 1, 0.1, 100)
  camera.position.set(0, 0.34, 3.05)
  camera.lookAt(0, 0, 0)

  // Tipped off-axis so the aperture is read as a dimensional object rather than a flat dial.
  const armature = new Group()
  armature.rotation.set(-0.42, 0, 0.16)
  armature.scale.set(1, 1.14, 1)
  scene.add(armature)

  /* --- Blades ------------------------------------------------------------ */
  const bladeBase = new TorusGeometry(1, 0.0055, 4, TUBULAR)
  const bladeGeo = new InstancedBufferGeometry()
  bladeGeo.index = bladeBase.index
  bladeGeo.setAttribute("position", bladeBase.attributes.position)
  bladeGeo.setAttribute("normal", bladeBase.attributes.normal)
  bladeGeo.instanceCount = BLADES

  const bladeI = new Float32Array(BLADES)
  const bladeR = new Float32Array(BLADES)
  for (let i = 0; i < BLADES; i += 1) {
    bladeI[i] = BLADES > 1 ? i / (BLADES - 1) : 0.5
    // Deterministic pseudo-random: the instrument should look the same on every load.
    bladeR[i] = (Math.sin(i * 127.1) * 43758.5453) % 1
    if (bladeR[i] < 0) bladeR[i] += 1
  }
  bladeGeo.setAttribute("aI", new InstancedBufferAttribute(bladeI, 1))
  bladeGeo.setAttribute("aR", new InstancedBufferAttribute(bladeR, 1))

  const palette = TONE_PALETTE.onDark
  const INK = new Color(palette.ink)
  const ACCENT = new Color(palette.accent)
  const HIGHLIGHT = new Color(palette.highlight)

  const shared = {
    uTime: { value: 0 },
    uOpen: { value: 0.36 },
    uTilt: { value: 0.52 },
    uOrder: { value: 0.62 },
    uFocus: { value: 0 },
    uWave: { value: 0 },
    uSpin: { value: 0.07 },
    uScatter: { value: 0.36 },
    uCharge: { value: 0.26 },
    uSweep: { value: 0 },
    uSweepEnergy: { value: 0 },
    uInk: { value: INK },
    uAccent: { value: ACCENT },
    uHighlight: { value: HIGHLIGHT },
  }

  const bladeMat = new ShaderMaterial({
    vertexShader: BLADE_VERTEX,
    fragmentShader: BLADE_FRAGMENT,
    transparent: true,
    depthWrite: false,
    uniforms: shared,
  })
  armature.add(new Mesh(bladeGeo, bladeMat))

  /* --- Nucleus ----------------------------------------------------------- */
  const shardBase = new OctahedronGeometry(1, 0)
  const coreGeo = new InstancedBufferGeometry()
  coreGeo.index = shardBase.index
  coreGeo.setAttribute("position", shardBase.attributes.position)
  coreGeo.setAttribute("normal", shardBase.attributes.normal)
  coreGeo.instanceCount = SHARDS

  const seeds = new Float32Array(SHARDS * 3)
  const shardR = new Float32Array(SHARDS)
  // Fibonacci sphere: an even, non-clustered distribution without needing a random table.
  const golden = Math.PI * (3 - Math.sqrt(5))
  for (let i = 0; i < SHARDS; i += 1) {
    const y = 1 - (i / (SHARDS - 1)) * 2
    const r = Math.sqrt(Math.max(1 - y * y, 0))
    const theta = golden * i
    seeds[i * 3] = Math.cos(theta) * r
    seeds[i * 3 + 1] = y
    seeds[i * 3 + 2] = Math.sin(theta) * r
    shardR[i] = i / SHARDS
  }
  coreGeo.setAttribute("aSeed", new InstancedBufferAttribute(seeds, 3))
  coreGeo.setAttribute("aR", new InstancedBufferAttribute(shardR, 1))

  const coreMat = new ShaderMaterial({
    vertexShader: CORE_VERTEX,
    fragmentShader: CORE_FRAGMENT,
    transparent: true,
    depthWrite: false,
    uniforms: shared,
  })
  armature.add(new Mesh(coreGeo, coreMat))

  let disposed = false
  let width = 0, height = 0, last = "", renders = 0
  return {
    ready: renderer.compileAsync(scene, camera).then(() => {}),
    draw(pose, progress) {
      if (disposed || document.hidden || renderer.getContext().isContextLost()) return false
      const w = canvas.clientWidth, h = canvas.clientHeight
      if (!w || !h) return false
      const key = JSON.stringify([pose, progress, w, h, window.devicePixelRatio])
      if (key === last) return true
      last = key
      if (w !== width || h !== height) {
        width = w; height = h
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5))
        renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix()
      }
      shared.uOpen.value = pose.open; shared.uTilt.value = pose.tilt
      shared.uSpin.value = pose.spin; shared.uScatter.value = pose.scatter
      shared.uOrder.value = pose.order; shared.uCharge.value = pose.charge
      shared.uFocus.value = pose.focus
      shared.uWave.value = .012 + (progress > 1.6 && progress < 2.4 ? .03 : 0)
      shared.uTime.value = 1.4 + progress * .8
      shared.uSweep.value = Math.max(0, progress - 4)
      shared.uSweepEnergy.value = progress > 4 ? Math.sin((progress - 4) * Math.PI) : 0
      armature.rotation.set(-.42, .35 + progress * .035, .16)
      const start = performance.now()
      renderer.render(scene, camera)
      canvas.dataset.renders = String(++renders)
      canvas.dataset.triangles = String(renderer.info.render.triangles)
      canvas.dataset.drawCalls = String(renderer.info.render.calls)
      canvas.dataset.maxRenderMs = String(Math.max(Number(canvas.dataset.maxRenderMs || 0), performance.now() - start))
      return true
    },
    dispose() {
      if (disposed) return
      disposed = true
      bladeBase.dispose(); shardBase.dispose(); bladeGeo.dispose(); coreGeo.dispose()
      bladeMat.dispose(); coreMat.dispose(); renderer.dispose()
    },
  }
}
