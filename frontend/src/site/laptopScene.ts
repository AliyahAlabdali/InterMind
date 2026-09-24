import {
  ACESFilmicToneMapping,
  AmbientLight,
  Box3,
  DirectionalLight,
  Mesh,
  MeshStandardMaterial,
  PerspectiveCamera,
  PointLight,
  Scene,
  SRGBColorSpace,
  Vector3,
  WebGLRenderer,
  Texture,
  DataTexture,
  HalfFloatType,
  RGBAFormat,
  LinearFilter,
  CubeUVReflectionMapping,
  LinearSRGBColorSpace,
} from "three"
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js"

import type { LaptopAssets } from "./journey/laptopAssets"

/** The lid's inner face in the source model. Everything on screen hangs off finding this. */
const SCREEN_MATERIAL = "Material.007"

/** The four corners of the screen, in canvas pixels, top-left first and clockwise. */
export type ScreenQuad = [
  [number, number],
  [number, number],
  [number, number],
  [number, number],
]

export interface LaptopSceneHandle {
  /** Pointer position, -0.5..0.5 on each axis. */
  setTilt: (x: number, y: number) => void
  setReveal: (progress: number) => void
  dispose: () => void
}

interface Options {
  reducedMotion: boolean
  assets: LaptopAssets
  signal?: AbortSignal
  onLost?: () => void
  /** Called once the model is on screen and the screen quad is first known. */
  onReady: () => void
  /** Called every frame the screen quad moves, so the DOM overlay can follow it. */
  onScreen: (quad: ScreenQuad) => void
}

/**
 * The hero's laptop: a real glTF model rather than a CSS approximation.
 *
 * The model supplies the geometry and nothing else. Its own screen texture is replaced by a
 * hole - the panel is rendered black and the InterMind interface is laid over it in the DOM,
 * mapped onto the panel's four projected corners. That keeps the interface as crisp vector text
 * at any zoom, keeps it the same markup the rest of the product uses, and means the screen never
 * has to be re-authored as a texture.
 *
 * Loaded on demand. three.js and a 2MB model have no business in the bundle that has to arrive
 * before the page can paint.
 */
export async function createLaptopScene(
  canvas: HTMLCanvasElement,
  { reducedMotion, assets, onReady, onScreen, signal, onLost }: Options,
): Promise<LaptopSceneHandle> {
  const begun = performance.now()
  canvas.dataset.modelLoadMs = assets.modelMs.toFixed(1)
  canvas.dataset.roomLoadMs = assets.roomMs.toFixed(1)
  signal?.throwIfAborted()
  const parseStart = performance.now()
  const gltf = await new GLTFLoader().parseAsync(assets.model, "/models/")
  canvas.dataset.modelParseMs = (performance.now() - parseStart).toFixed(1)
  const rendererStart = performance.now()
  const renderer = new WebGLRenderer({ canvas, antialias: true, alpha: true })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5))
  renderer.outputColorSpace = SRGBColorSpace
  renderer.toneMapping = ACESFilmicToneMapping
  renderer.toneMappingExposure = 1.0
  canvas.dataset.rendererInitMs = (performance.now() - rendererStart).toFixed(1)
  const environmentStart = performance.now()

  const scene = new Scene()

  // A medium lens. Product photography is not shot at 60 degrees, and a wide field here would
  // throw the near corner of the deck at the viewer exactly like the CSS build used to.
  const camera = new PerspectiveCamera(26, 1, 0.1, 100)

  // Exact half-float PMREM data baked from this laptop's original darkRoom recipe.
  // Uploading it avoids repeating the expensive environment convolution on every mount.
  const header = new Uint32Array(assets.room, 0, 2)
  const environment = new DataTexture(new Uint16Array(assets.room, 8), header[0], header[1], RGBAFormat, HalfFloatType)
  environment.mapping = CubeUVReflectionMapping
  environment.minFilter = LinearFilter; environment.magFilter = LinearFilter
  environment.colorSpace = LinearSRGBColorSpace
  environment.generateMipmaps = false; environment.needsUpdate = true
  scene.environment = environment
  canvas.dataset.environmentMs = (performance.now() - environmentStart).toFixed(1)

  // Lighting a near-black object on a near-black page.
  //
  // Fill does not work here: raising it turns the anodised chassis silver, which is what the
  // first pass did. What separates the machine from the background is its edges - so the work is
  // done by a raking key that catches the top surfaces and two rim lights behind it that draw
  // the silhouette in the product's own indigo and cyan.
  scene.add(new AmbientLight(0x241f38, 0.65))

  const key = new DirectionalLight(0xdfe7f5, 2.0)
  key.position.set(2.6, 4.0, 2.4)
  scene.add(key)

  // Behind and above, picking out the top edge of the lid and the far corner of the deck.
  const rim = new DirectionalLight(0xcfd9ef, 2.6)
  rim.position.set(-2.2, 2.6, -3.4)
  scene.add(rim)

  const indigo = new PointLight(0x7d6fd0, 26, 24)
  indigo.position.set(-3.4, 1.2, 1.6)
  scene.add(indigo)

  const cyan = new PointLight(0x5ad7e0, 11, 18)
  cyan.position.set(2.6, -0.4, 2.2)
  scene.add(cyan)

  const model = gltf.scene
  // Keep materials replaced for the DOM screen reachable for final disposal.
  const replacedMaterials: MeshStandardMaterial[] = []

  let screenMesh: Mesh | null = null

  model.traverse((child) => {
    if (!(child instanceof Mesh)) return
    const material = child.material as MeshStandardMaterial | MeshStandardMaterial[]
    const first = Array.isArray(material) ? material[0] : material

    if (first?.name === SCREEN_MATERIAL) {
      screenMesh = child
      replacedMaterials.push(...(Array.isArray(material) ? material : [material]))
      // The panel becomes a black hole for the DOM interface to sit in. Its own wallpaper is
      // replaced so its wallpaper is never uploaded to the GPU.
      const blank = new MeshStandardMaterial({ color: 0x000000, roughness: 0.28, metalness: 0 })
      blank.map = null
      child.material = blank
      return
    }

    // The chassis keeps the model's own dark finish, nudged toward the product's charcoal and
    // away from a showroom shine. Anything already textured (the key legends) is left alone.
    if (first && !first.map) {
      first.metalness = Math.min(first.metalness ?? 0.6, 0.55)
      first.roughness = Math.max(first.roughness ?? 0.4, 0.42)
      first.envMapIntensity = 1
    }
  })

  if (!screenMesh) {
    renderer.dispose()
    environment.dispose()
    throw new Error(`laptop.glb: no mesh using ${SCREEN_MATERIAL}`)
  }

  scene.add(model)

  // Frame the machine: centre it on the origin and pull the camera back until it fills a known
  // fraction of the view. Doing it from the model's own bounds rather than from hard-coded
  // numbers is what lets the framing survive a different model.
  const box = new Box3().setFromObject(model)
  const size = box.getSize(new Vector3())
  const centre = box.getCenter(new Vector3())
  model.position.sub(centre)

  const radius = Math.max(size.x, size.y, size.z)
  const distance = (radius / Math.tan((camera.fov * Math.PI) / 360)) * 0.78

  /** A three-quarter view: round to the right, slightly above eye level. */
  const YAW = 0.2
  const PITCH = 0.3

  /**
   * Where the camera stands before the opening turn, as offsets from that resting view.
   *
   * The machine arrives at a hard three-quarter angle, seen from further out and further above,
   * and one restrained move brings it round to face the viewer. The numbers are a single partial
   * turn on purpose: 54 degrees is enough that the lid, the deck and the near edge all read as
   * one solid object being turned, and little enough that it never becomes a spin. Anything that
   * carried the camera past the machine's profile would be a showreel rather than a product shot.
   *
   * At progress 1 every term is zero, so the resting hero pose is exactly the one it always was.
   */
  const OPEN_YAW = 0.95
  const OPEN_PITCH = 0.2
  const OPEN_DOLLY = 0.17

  const tilt = { x: 0, y: 0 }
  const eased = { x: 0, y: 0 }

  // The panel's own corners, in its local space, read once from its geometry.
  const mesh = screenMesh as Mesh
  mesh.geometry.computeBoundingBox()
  const gb = mesh.geometry.boundingBox!
  const localCorners = [
    new Vector3(gb.min.x, gb.max.y, gb.max.z),
    new Vector3(gb.max.x, gb.max.y, gb.max.z),
    new Vector3(gb.max.x, gb.min.y, gb.min.z),
    new Vector3(gb.min.x, gb.min.y, gb.min.z),
  ]
  const world = new Vector3()

  function resize() {
    const w = canvas.clientWidth
    const h = canvas.clientHeight
    if (!w || !h) return
    // The pixel ratio is re-read here, not just at construction: a window dragged to a display
    // with a different density would otherwise keep rendering at the old one and go soft.
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5))
    renderer.setSize(w, h, false)
    camera.aspect = w / h
    camera.updateProjectionMatrix()
    invalidate()
  }

  let raf = 0, reveal = 1, disposed = false, lost = false, active = false
  let announced = false, last = "", renders = 0
  function invalidate() {
    if (!disposed && !lost && active && !document.hidden && !raf) raf = requestAnimationFrame(frame)
  }
  function frame() {
    raf = 0
    if (disposed || lost || !active || document.hidden) return

    // The whole assembly turns a few degrees under the pointer. Small on purpose: this is a lit
    // object being turned, not a model the viewer is meant to orbit.
    eased.x += (tilt.x - eased.x) * 0.07
    eased.y += (tilt.y - eased.y) * 0.07

    const opening = 1 - reveal
    const yaw = YAW + eased.x * 0.26 + opening * OPEN_YAW
    const pitch = PITCH - eased.y * 0.16 + opening * OPEN_PITCH
    const range = distance * (1 + opening * OPEN_DOLLY)
    camera.position.set(
      Math.sin(yaw) * Math.cos(pitch) * range,
      Math.sin(pitch) * range,
      Math.cos(yaw) * Math.cos(pitch) * range,
    )
    camera.lookAt(0, 0, 0)
    camera.updateMatrixWorld()

    const started = performance.now()
    renderer.render(scene, camera)
    canvas.dataset.renders = String(++renders)
    canvas.dataset.triangles = String(renderer.info.render.triangles)
    canvas.dataset.drawCalls = String(renderer.info.render.calls)
    canvas.dataset.maxRenderMs = String(Math.max(Number(canvas.dataset.maxRenderMs || 0), performance.now() - started))

    // Project the panel's corners so the DOM interface can be laid onto them. Done after the
    // render so the matrices are the ones actually drawn this frame.
    const w = canvas.clientWidth
    const h = canvas.clientHeight
    const quad = localCorners.map((corner) => {
      world.copy(corner)
      mesh.localToWorld(world)
      world.project(camera)
      return [((world.x + 1) / 2) * w, ((-world.y + 1) / 2) * h] as [number, number]
    }) as ScreenQuad

    // Only wake React when the projection has actually moved.
    const key = quad.map(([x, y]) => `${x | 0},${y | 0}`).join("|")
    if (key !== last) {
      last = key
      onScreen(quad)
    }

    if (!announced) {
      announced = true
      canvas.dataset.firstFrameMs = (performance.now() - begun).toFixed(1)
      onReady()
    }

    if (Math.abs(tilt.x - eased.x) > .001 || Math.abs(tilt.y - eased.y) > .001) invalidate()
  }
  const observer = new ResizeObserver(resize)
  const gate = new IntersectionObserver(([entry]) => {
    active = entry.isIntersecting
    canvas.parentElement?.toggleAttribute("data-paused", !active)
    if (active) invalidate(); else { cancelAnimationFrame(raf); raf = 0 }
  })
  const visibility = () => {
    canvas.parentElement?.toggleAttribute("data-paused", document.hidden || !active)
    if (document.hidden) { cancelAnimationFrame(raf); raf = 0 } else invalidate()
  }
  const contextLost = (event: Event) => {
    event.preventDefault(); lost = true; announced = false
    cancelAnimationFrame(raf); raf = 0; onLost?.()
  }
  const contextRestored = () => { lost = false; last = ""; resize(); invalidate() }
  document.addEventListener("visibilitychange", visibility)
  canvas.addEventListener("webglcontextlost", contextLost)
  canvas.addEventListener("webglcontextrestored", contextRestored)
  function dispose() {
    if (disposed) return
    disposed = true; cancelAnimationFrame(raf); observer.disconnect(); gate.disconnect()
    document.removeEventListener("visibilitychange", visibility)
    canvas.removeEventListener("webglcontextlost", contextLost)
    canvas.removeEventListener("webglcontextrestored", contextRestored)
    signal?.removeEventListener("abort", dispose)
    const textures = new Set<Texture>()
    for (const material of replacedMaterials) {
      for (const value of Object.values(material)) if (value instanceof Texture) textures.add(value)
      material.dispose()
    }
    scene.traverse(child => {
      if (!(child instanceof Mesh)) return
      child.geometry.dispose()
      for (const material of Array.isArray(child.material) ? child.material : [child.material]) {
        for (const value of Object.values(material)) if (value instanceof Texture) textures.add(value)
        material.dispose()
      }
    })
    textures.forEach(texture => texture.dispose())
    environment.dispose(); renderer.dispose()
  }
  const compileStart = performance.now()
  try { await renderer.compileAsync(scene, camera) } catch (error) { dispose(); throw error }
  canvas.dataset.shaderCompileMs = (performance.now() - compileStart).toFixed(1)
  observer.observe(canvas); gate.observe(canvas); resize()
  signal?.addEventListener("abort", dispose, { once: true })
  if (signal?.aborted) dispose()
  return {
    setTilt(x, y) { if (reducedMotion || reveal < 1) return; tilt.x = x; tilt.y = y; invalidate() },
    setReveal(progress) {
      if (reveal === progress) return
      reveal = progress
      tilt.x = 0; tilt.y = 0; eased.x = 0; eased.y = 0
      invalidate()
    },
    dispose,
  }
}
