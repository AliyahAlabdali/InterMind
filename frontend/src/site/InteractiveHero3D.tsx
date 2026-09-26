import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react"
import { usePrefersReducedMotion } from "../hooks/usePrefersReducedMotion"
import { useMediaQuery } from "../hooks/useMediaQuery"
import { useDesktopMotion } from "./journey/useDesktopMotion"
import { loadLaptopAssets } from "./journey/laptopAssets"
import { INTRO_STEP, type IntroPhase } from "./journey/useLandingIntro"
import type { LaptopSceneHandle, ScreenQuad } from "./laptopScene"

/**
 * The hero: a real laptop, with the product running on it.
 *
 * The machine is a glTF model rendered with three.js. The interface on its screen is not a
 * texture - it is the same DOM and SVG the rest of the product is built from, laid over the
 * model's display panel by mapping it onto the panel's four projected corners every frame. That
 * keeps the interface crisp vector at any zoom, and means the screen never has to be re-authored
 * as an image when the product changes.
 *
 * The floating cards hang off the same projection, so they stay attached to the screen as the
 * machine turns under the pointer.
 *
 * Everything here is decorative. The hero's meaning is carried by the headline beside it, so the
 * whole assembly is hidden from assistive technology rather than described.
 */

/**
 * The DOM screen's own size. Its aspect matches the model's display panel (4.0158 x 2.7581 in
 * model units), so the mapping below places the interface on the panel without stretching it.
 */
const PANEL_ASPECT = 4.0158 / 2.7581
const SCREEN_W = 560
const SCREEN_H = Math.round(SCREEN_W / PANEL_ASPECT)

/**
 * How large the floating cards are drawn relative to the display they annotate. They are sized
 * to the machine so they do not swamp it on a small screen, and then lifted by this so they stay
 * legible rather than shrinking into the render. The scale is capped at 1 further down, so a
 * card never draws larger than the size it was actually designed at.
 */
const CARD_GAIN = 1.72

/**
 * How long the opening turn takes, and how long an interrupted one has left to resolve.
 *
 * The turn is deliberately slower than a transition: it is the one moment the visitor is asked
 * to watch an object move, and at anything under a second it reads as a glitch rather than a
 * reveal. If the visitor cuts the opening short the remainder is closed off quickly instead,
 * because at that point they have said they would rather be looking at the page.
 */
const TURN_MS = 1150
const RESOLVE_MS = 380

/**
 * Where each floating card comes from, as a fraction of its distance back to the middle of the
 * display, and the furthest it is allowed to travel in stage pixels.
 *
 * The cards are the analysis, so they have to look like they came out of the interview rather
 * than off the edges of the page. Each one starts pulled back toward the screen it annotates and
 * arrives at the position it holds for the rest of the visit, which gives every card an origin
 * and a destination instead of a fade. The cap keeps that honest on a wide viewport, where the
 * untrimmed vector would throw a card across the whole stage.
 */
const CARD_ORIGIN_PULL = 0.62
const CARD_ORIGIN_MAX = 118

/**
 * Portrait framing for the flat composition.
 *
 * `PORTRAIT_CROP` is how much of the 676-wide artwork a phone is shown. Scaling to the full
 * width fitted the whole desk on screen at half size; scaling to this narrower window fills the
 * stage with the machine instead and lets the parent crop the edges, which is the difference
 * between a picture of a laptop and a laptop.
 *
 * The window is deliberately only a little wider than the display panel itself (which spans
 * roughly x 192..537 of the artwork). That leaves a margin of about 60px of artwork either side
 * - enough for the cards to hang off the device's edges without being cropped, and not so much
 * that the machine shrinks back into the middle of the stage.
 *
 * `PORTRAIT_LIFT` then slides the artwork up so the display - the part that carries the meaning,
 * because the live interface is drawn on it - clears the top of the stage rather than sitting in
 * the middle of it behind the fold.
 */
const PORTRAIT_CROP = 424
const PORTRAIT_LIFT = -106

const SKY = "#bfcde0"
const INDIGO = "#3b3355"
const GRAPE = "#5d5d81"
const CYAN = "#6ee7f0"
const VIOLET = "#a78bfa"
const CORE = "#818cf8"

/**
 * The CSS transform that lays a rectangle onto an arbitrary four-sided shape.
 *
 * A screen seen in perspective is not a scaled rectangle - its far edge is shorter than its near
 * one - so no combination of translate, scale and rotate will fit the interface to it. What does
 * fit is a projective transform, and solving for one from four point pairs is eight linear
 * equations. The result drops straight into `matrix3d`, which is why the interface sits on the
 * panel exactly rather than approximately.
 */
function quadTransform(w: number, h: number, quad: ScreenQuad): string {
  const src: Array<[number, number]> = [
    [0, 0],
    [w, 0],
    [w, h],
    [0, h],
  ]
  const a: number[][] = []
  const b: number[] = []
  for (let i = 0; i < 4; i += 1) {
    const [x, y] = src[i]
    const [u, v] = quad[i]
    a.push([x, y, 1, 0, 0, 0, -x * u, -y * u])
    b.push(u)
    a.push([0, 0, 0, x, y, 1, -x * v, -y * v])
    b.push(v)
  }

  // Gaussian elimination with partial pivoting. Eight equations is small enough that this is
  // both the clearest and the fastest thing to do.
  for (let col = 0; col < 8; col += 1) {
    let pivot = col
    for (let row = col + 1; row < 8; row += 1) {
      if (Math.abs(a[row][col]) > Math.abs(a[pivot][col])) pivot = row
    }
    const rowA = a[col]
    a[col] = a[pivot]
    a[pivot] = rowA
    const rowB = b[col]
    b[col] = b[pivot]
    b[pivot] = rowB
    if (Math.abs(a[col][col]) < 1e-10) return "none"
    for (let row = 0; row < 8; row += 1) {
      if (row === col) continue
      const f = a[row][col] / a[col][col]
      for (let k = col; k < 8; k += 1) a[row][k] -= f * a[col][k]
      b[row] -= f * b[col]
    }
  }
  const m = b.map((value, i) => value / a[i][i])

  // matrix3d is column-major, and the projective terms live in the fourth row.
  const t = [m[0], m[3], 0, m[6], m[1], m[4], 0, m[7], 0, 0, 1, 0, m[2], m[5], 0, 1]
  return `matrix3d(${t.map((v) => (Math.abs(v) < 1e-9 ? 0 : Number(v.toFixed(8)))).join(",")})`
}

/** A point inside - or just outside - the screen quad, in canvas pixels. */
function atUV(quad: ScreenQuad, u: number, v: number): [number, number] {
  const topX = quad[0][0] + (quad[1][0] - quad[0][0]) * u
  const topY = quad[0][1] + (quad[1][1] - quad[0][1]) * u
  const botX = quad[3][0] + (quad[2][0] - quad[3][0]) * u
  const botY = quad[3][1] + (quad[2][1] - quad[3][1]) * u
  return [topX + (botX - topX) * v, topY + (botY - topY) * v]
}

export function InteractiveHero3D({ className = "", phase = "settled" }: { className?: string; phase?: IntroPhase }) {
  const reducedMotion = usePrefersReducedMotion()
  const enabled = useDesktopMotion()
  // Matches the 639px breakpoint landing.css uses for the portrait hero, so the framing below
  // and the stage height it is framed into can never disagree about which layout is on screen.
  const portrait = useMediaQuery("(max-width: 639px)")
  const step = INTRO_STEP[phase]

  // The opening's beats, as the things on screen rather than as phase names. The screen lights
  // while the machine is still finishing its turn; the voice channel, then what was said, then
  // what it showed, arrive one after another, so the visitor reads a sequence and not a state.
  const lit = step >= INTRO_STEP.wake
  const heard = step >= INTRO_STEP.listen
  const assessed = step >= INTRO_STEP.analyze
  // Once the composition is on its way to the hero the stagger has done its job, so anything
  // still outstanding - after a skip, most of all - lands together rather than in slow motion.
  const stagger = step < INTRO_STEP.dock

  const hostRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const sceneRef = useRef<LaptopSceneHandle | null>(null)
  const revealRef = useRef(step > INTRO_STEP.brand ? 1 : 0)
  const [quad, setQuad] = useState<ScreenQuad | null>(null)
  const [ready, setReady] = useState(false)
  const [failed, setFailed] = useState(false)
  const [stageW, setStageW] = useState(0)

  useLayoutEffect(() => {
    const host = hostRef.current
    const slot = host?.parentElement
    if (!host || !slot || phase === "settled") return
    // offset geometry stays stable while the composition is temporarily translated.
    const section = slot.closest<HTMLElement>(".landing-hero")
    const sectionLeft = section?.offsetLeft ?? 0
    slot.style.setProperty("--intro-x", `${innerWidth / 2 - sectionLeft - slot.offsetLeft - slot.offsetWidth / 2}px`)
  }, [phase])

  useEffect(() => {
    const host = hostRef.current
    if (!host) return
    const observer = new ResizeObserver(() => setStageW(host.clientWidth))
    observer.observe(host)
    setStageW(host.clientWidth)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !enabled) return
    let cancelled = false
    const controller = new AbortController()

    const importStart = performance.now()
    // Fetch immutable assets and import Three in parallel while the intro name is visible.
    const assets = loadLaptopAssets()
    const sceneModule = import("./laptopScene").then(module => {
      canvas.dataset.importMs = (performance.now() - importStart).toFixed(1)
      return module
    })
    void Promise.all([sceneModule, assets]).then(async ([{ createLaptopScene }, prepared]) => {
      if (cancelled) return
      canvas.dataset.importAndAssetsMs = (performance.now() - importStart).toFixed(1)
      canvas.dataset.initializations = String(Number(canvas.dataset.initializations || 0) + 1)
      const handle = await createLaptopScene(canvas, {
        reducedMotion, assets: prepared, signal: controller.signal,
        onLost: () => { if (!cancelled) setReady(false) },
        onReady: () => {
          if (!cancelled) { canvas.dataset.visibleFrameMs = (performance.now() - importStart).toFixed(1); setReady(true); setFailed(false) }
        },
        onScreen: next => { if (!cancelled) setQuad(next) },
      })
      if (cancelled) { handle.dispose(); return }
      sceneRef.current = handle
      handle.setReveal(revealRef.current)
    }).catch(error => { if (!cancelled) { canvas.dataset.loadError = String(error); setFailed(true) } })

    return () => {
      cancelled = true
      controller.abort()
      sceneRef.current?.dispose()
      sceneRef.current = null
    }
  }, [reducedMotion, enabled])

  /**
   * The opening turn.
   *
   * Driven from here rather than from the scene so the scene stays a pure renderer with no
   * timeline of its own, and so the turn keeps running across the phase changes that happen
   * while it is still in flight. It depends on whether the turn has been released and whether
   * the composition has started docking, and on nothing else: re-running it on every beat would
   * restart the easing from a standstill part way through and read as a stutter.
   *
   * A full turn eases in and out, which is a camera move. A turn cut short by the visitor eases
   * out only, from wherever it had got to, because it is now finishing rather than performing.
   */
  const turning = step >= INTRO_STEP.reveal
  const docking = step >= INTRO_STEP.dock
  useEffect(() => {
    const set = (value: number) => { revealRef.current = value; sceneRef.current?.setReveal(value) }
    if (!enabled || reducedMotion) { set(1); return }
    const from = revealRef.current
    const to = turning ? 1 : 0
    if (from === to) return
    // Taking up the opening pose is not part of the story: nothing is on screen yet.
    if (!turning) { set(0); return }
    let frame = 0
    const started = performance.now()
    const span = docking ? RESOLVE_MS : TURN_MS
    const animate = (now: number) => {
      const t = Math.min(1, (now - started) / span)
      const eased = docking ? 1 - Math.pow(1 - t, 3) : 0.5 - Math.cos(Math.PI * t) / 2
      set(from + (to - from) * eased)
      if (t < 1) frame = requestAnimationFrame(animate)
    }
    frame = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(frame)
  }, [turning, docking, enabled, reducedMotion])

  const handleMove = useCallback((event: React.MouseEvent<HTMLDivElement>) => {
    const host = hostRef.current
    if (!host) return
    const rect = host.getBoundingClientRect()
    sceneRef.current?.setTilt(
      (event.clientX - rect.left) / rect.width - 0.5,
      (event.clientY - rect.top) / rect.height - 0.5,
    )
  }, [])

  const handleLeave = useCallback(() => sceneRef.current?.setTilt(0, 0), [])

  const screenStyle = useMemo(() => {
    if (!quad) return undefined
    return {
      width: SCREEN_W,
      height: SCREEN_H,
      transformOrigin: "0 0",
      transform: quadTransform(SCREEN_W, SCREEN_H, quad),
    }
  }, [quad])

  const visible = Boolean(enabled && ready && quad && !failed)
  const fallbackQuad: ScreenQuad = [[192.38,137.74],[536.92,150.32],[526.52,380.61],[200.50,357.80]]

  return (
    <div
      ref={hostRef}
      aria-hidden="true"
      onMouseMove={reducedMotion ? undefined : handleMove}
      onMouseLeave={reducedMotion ? undefined : handleLeave}
      data-laptop-ready={visible ? "true" : undefined}
      data-stage={phase}
      className={`hero-stage relative ${className}`}
    >
      {/* The room's own halo, so the machine reads as lit rather than pasted onto black. */}
      <span
        aria-hidden="true"
        className="stage-veil pointer-events-none absolute left-1/2 top-1/2 h-[104%] w-[104%] -translate-x-1/2 -translate-y-1/2 rounded-full"
      />

      {/* No WebGL, no desktop motion, or a scene that failed: the same composition, drawn flat.
          It still plays the opening's beats, because the story is the interview waking up and
          being read, and none of that depends on the machine being a real model. */}
      {!visible && <div className="laptop-fallback absolute inset-0 overflow-hidden">
        {/* Landscape art, composed twice. Uniformly scaling the 676-wide artwork to a phone put
            it at half size in the middle of the stage, which is what made the machine read as a
            small picture sitting under the copy rather than as the product.

            Portrait instead crops rather than shrinks - the same artwork is scaled to a narrower
            window and anchored to the top of the stage, so the screen and the cards rise into
            the first viewport while the empty desk below falls off the fold. The overflow-hidden
            parent does the cropping; nothing is redrawn and no second asset is loaded. */}
        <div
          className={portrait ? "absolute left-1/2 top-0" : "absolute left-1/2 top-1/2"}
          style={{
            width: 676, height: 600,
            transform: portrait
              ? `translate(-50%, ${PORTRAIT_LIFT}px) scale(${Math.min(stageW / PORTRAIT_CROP, 1)})`
              : `translate(-50%, -50%) scale(${Math.min(stageW / 676, 1)})`,
            transformOrigin: portrait ? "50% 0" : undefined,
          }}
        >
          <img src="/models/laptop-image.png" alt="" width="676" height="600" className="absolute inset-0" />
          <div className="hero-screen absolute left-0 top-0" data-lit={lit ? "true" : undefined} style={{ width: SCREEN_W, height: SCREEN_H, transformOrigin: "0 0", transform: quadTransform(SCREEN_W, SCREEN_H, fallbackQuad) }}><Screen /></div>
          {/* Portrait brings the cards inside the display's own footprint. The desktop values put
              them well outside it - `u` of -0.8 and 1.8 are off either side of the screen - which
              is right on a stage wider than the artwork and wrong here, where the crop window is
              narrower than the artwork and anything outside `u` 0..1 lands in the cropped-away
              margin. That is what produced the clipped card fragments along the top edge.

              So on a phone they straddle the machine's edges rather than sitting squarely on it:
              the transcript hangs off the left bezel, the competency dial off the right, and the
              live channel floats below the display across the hinge. Each one overlaps the
              device enough to be attached to it and breaks its outline enough to read as a
              signal coming off it rather than a panel pasted onto it.

              They are also drawn a little smaller than the desktop cards. On a stage this size
              the machine has to stay the subject; a card that competes with it for width stops
              being an annotation. */}
          {/* Entrance, portrait only. Each card arrives from the side it lives on - transcript
              from the left, competency from the right, the live channel up from under the hinge
              a beat later - instead of converging from the middle of the display, which on a
              stage this size is a move of a few pixels and reads as no move at all.

              The arrival order is also portrait's own: both side cards at `listen`, staggered,
              and the channel at `analyze`. Desktop keeps the order it had. */}
          <Floating quad={fallbackQuad} stage={676} width={portrait ? 222 : 292} u={.5} v={portrait ? 1.24 : -.3} align="centre" depth={0}
            emerged={portrait ? assessed : heard}
            delay={portrait ? 120 : 0}
            from={portrait ? { x: 0, y: 86, z: -40 } : undefined}><WaveformPill /></Floating>
          <Floating quad={fallbackQuad} stage={676} width={portrait ? 196 : 228} u={portrait ? -.05 : -.8} v={portrait ? .68 : -.46} depth={0}
            emerged={portrait ? heard : assessed}
            delay={0}
            from={portrait ? { x: -132, y: 18, z: -30 } : undefined}><TranscriptPanel /></Floating>
          <Floating quad={fallbackQuad} stage={676} width={portrait ? 140 : 188} u={portrait ? .9 : 1.8} v={portrait ? .14 : -.52} align="end" depth={0}
            emerged={portrait ? heard : assessed}
            delay={portrait ? 190 : (stagger ? 420 : 0)}
            from={portrait ? { x: 132, y: 10, z: -30 } : undefined}><RadialPanel /></Floating>
        </div>
      </div>}
      {enabled && <canvas
        ref={canvasRef}
        className={`absolute inset-0 h-full w-full transition-opacity duration-700 ${
          visible ? "opacity-100" : "opacity-0"
        }`}
      />}

      {/* The interface, laid onto the model's display panel. It lights a beat before the turn
          has finished, so the machine is still moving when the interview appears on it. */}
      <div
        className={`hero-screen pointer-events-none absolute left-0 top-0 transition-opacity duration-500 ${
          visible ? "opacity-100" : "opacity-0"
        }`}
        data-lit={lit ? "true" : undefined}
        style={screenStyle}
      >
        <Screen />
      </div>

      {/* The floating cards, anchored to the same projection so they stay attached to the screen
          as the machine turns. They are deliberately not warped onto the panel: they read as a
          layer in front of the machine, which is what they were before.

          Written in the order they arrive, which is also the order the product works in: the
          candidate is speaking, then what they said has been read, then what it showed about one
          requirement. Getting all three at once would say nothing about any of it. */}
      {quad && (
        <div
          className={`hero-cards pointer-events-none absolute inset-0 transition-opacity duration-500 ${
            visible ? "opacity-100" : "opacity-0"
          }`}
        >
          <Floating
            quad={quad}
            stage={stageW}
            width={292}
            u={0.5}
            v={-0.3}
            align="centre"
            depth={140}
            emerged={heard}
            delay={0}
          >
            <WaveformPill />
          </Floating>
          <Floating
            quad={quad}
            stage={stageW}
            width={228}
            u={-0.8}
            v={-0.46}
            depth={112}
            emerged={assessed}
            delay={0}
          >
            <TranscriptPanel />
          </Floating>
          <Floating
            quad={quad}
            stage={stageW}
            width={188}
            u={1.8}
            v={-0.52}
            align="end"
            depth={126}
            emerged={assessed}
            delay={stagger ? 420 : 0}
          >
            <RadialPanel />
          </Floating>
        </div>
      )}
    </div>
  )
}

/**
 * Places one card at a point on the screen quad.
 *
 * The card is also scaled by how large the display is drawn, because the cards were designed
 * against a fixed stage and the machine now resizes with the viewport. Without this they hold
 * their pixel size while the laptop shrinks, and end up swamping the screen they are meant to
 * annotate.
 */
function Floating({
  quad,
  stage,
  width,
  u,
  v,
  align = "start",
  depth,
  emerged,
  delay,
  from,
  children,
}: {
  quad: ScreenQuad
  /** The stage's width in pixels, so a card can be kept inside it. */
  stage: number
  /** The card's own unscaled width, which is what the offset and clamp below are measured in. */
  width: number
  u: number
  v: number
  /** Which edge of the card the anchor refers to. */
  align?: "start" | "centre" | "end"
  /** How far in front of the machine the card floats, in pixels of translateZ. */
  depth: number
  /** Whether this card has been reached by the opening yet. False holds it at its origin. */
  emerged: boolean
  /** Where this card falls in the arrival stagger, in milliseconds. */
  delay: number
  /**
   * An explicit entrance origin, in stage pixels, instead of the computed one.
   *
   * The default origin is "pulled back toward the middle of the display", which reads correctly
   * on a wide stage where the cards sit outside the machine and converge onto it. In portrait
   * they sit *on* the machine, so converging from its centre is a move of a few pixels - which
   * is exactly why the opening looked like a still image on a phone. Portrait passes a direction
   * instead: in from the side it belongs to, or up from under the hinge.
   */
  from?: { x: number; y: number; z?: number }
  children: React.ReactNode
}) {
  const [x, y] = atUV(quad, u, v)
  const drawnWidth = Math.hypot(quad[1][0] - quad[0][0], quad[1][1] - quad[0][1])
  const scale = Math.max(0.35, Math.min(0.86, (drawnWidth / SCREEN_W) * CARD_GAIN))

  // How wide the card actually came out, rather than how wide it was predicted to be.
  //
  // Predicting it from `width * scale` was close but not exact - the card's own box, its
  // backdrop and the entrance's residual transform all move the number - and a clamp fed a
  // wrong width lets the card past the edge it was supposed to stop at. Measuring removes the
  // guess. Only while the entrance is over, so the animation's intermediate sizes are not
  // mistaken for the resting one.
  const cardRef = useRef<HTMLDivElement>(null)
  const [measured, setMeasured] = useState(0)
  useLayoutEffect(() => {
    const el = cardRef.current
    if (!el) return
    const w = el.getBoundingClientRect().width
    // Compared against the previous value rather than the one captured in this closure, so the
    // effect cannot chase its own stale reading round in a loop.
    if (w > 0) setMeasured((prev) => (Math.abs(w - prev) > 1 ? w : prev))
  }, [scale])

  // Alignment is done in pixels, not percentages. This wrapper has no size of its own - the card
  // inside it is absolutely positioned, so the wrapper shrinks to nothing - and a percentage
  // translate would resolve against that zero and move nothing at all.
  const drawn = measured || width * scale
  const margin = 6
  let px = x - (align === "centre" ? drawn / 2 : align === "end" ? drawn : 0)
  if (stage > 0) {
    // Once the camera is turned, the screen's centre is not the stage's centre, so on a narrow
    // viewport a card anchored near the display's right edge runs past the stage and is cut off
    // by the page. Clamping from the card's own width avoids having to measure the DOM.
    if (px + drawn > stage - margin) px = stage - margin - drawn
    if (px < margin) px = margin
  }

  // Where the card comes from: back along the line to the middle of the display, so it reads as
  // having been produced by the interview rather than having flown in from off the page. The
  // travel is capped in stage pixels and then divided by `scale`, because the offset is applied
  // inside a wrapper the scale has already been spent on.
  const [cx, cy] = atUV(quad, 0.5, 0.5)
  const pull = (delta: number) =>
    `${(Math.max(-CARD_ORIGIN_MAX, Math.min(CARD_ORIGIN_MAX, delta * CARD_ORIGIN_PULL)) / scale).toFixed(1)}px`
  // An explicit origin is still divided by `scale` for the same reason the computed one is: the
  // offset is applied inside a wrapper the scale has already been spent on.
  const offset = (value: number) => `${(value / scale).toFixed(1)}px`

  return (
    <div
      className="absolute left-0 top-0"
      style={{
        transform: `translate(${px}px, ${y}px) scale(${scale.toFixed(3)})`,
        perspective: depth * 8,
      }}
    >
      {/* Thrown forward out of the display rather than faded in place: the card starts behind
          the screen, small and dark, and arrives at the front. Position and entrance live on
          separate elements so neither can overwrite the other's transform.

          It settles at z 0 rather than out at `depth`. Under a perspective whose origin sits on
          this zero-sized wrapper, a resting translateZ would magnify the card and walk it away
          from its anchor, which breaks both its size and the clamp that keeps it on stage. The
          depth reads during the throw, which is where it is doing work. */}
      <div
        className="hero-panel-content"
        data-emerged={emerged ? "true" : undefined}
        style={{
          transformStyle: "preserve-3d",
          "--from-x": from ? offset(from.x) : pull(cx - px - drawn / 2),
          "--from-y": from ? offset(from.y) : pull(cy - y),
          "--from-z": `${(-Math.max(70, from ? -(from.z ?? 0) : depth * 0.8)).toFixed(0)}px`,
          "--emerge-delay": `${delay}ms`,
        } as React.CSSProperties}
      >
        <div ref={cardRef}>{children}</div>
      </div>
    </div>
  )
}

/**
 * What is on the screen: the interviewer, listening. The same glyph the candidate meets in the
 * interview room, so the hero is showing the product rather than an illustration of it.
 */
function Screen() {
  return (
    <div
      className="relative flex h-full w-full flex-col items-center justify-center gap-2 overflow-hidden rounded-[5px]"
      style={{ background: "#000000" }}
    >
      {/* The interviewer's own field, dimmed to screen brightness. */}
      <span
        className="pointer-events-none absolute left-1/2 top-1/2 h-[150%] w-[150%] -translate-x-1/2 -translate-y-1/2 rounded-full opacity-70"
        style={{
          background: `radial-gradient(50% 50% at 50% 50%, ${INDIGO} 0%, rgba(59,51,85,0) 70%)`,
          filter: "blur(12px)",
        }}
      />

      <InterviewerCore />

      {/* The state the candidate actually meets. During the opening it arrives just after the
          rest of the screen, so the display reads as coming on and then starting work. The
          wrapper exists to carry that delay: the chip's own pulse is an animation, and a
          transition on the same element would lose to it. */}
      <span className="screen-listen relative">
        <span className="hud-listen flex items-center gap-2">
          <span className="h-[5px] w-[5px] rounded-full" style={{ background: CYAN }} />
          <span
            className="text-[9px] font-medium uppercase"
            style={{ color: SKY, letterSpacing: "0.22em" }}
          >
            Listening
          </span>
        </span>
      </span>
    </div>
  )
}

/**
 * The interviewer itself, drawn as SVG.
 *
 * This is the instrument from the interview room rather than an icon standing in for it: a
 * gyroscopic cage of thin rings carried on crossing axes around a suspended nucleus of shards.
 * The rings never resolve into a concentric stack - each holds its own inclination, radius and
 * period - because that asymmetry is most of what makes it read as an instrument rather than an
 * orb.
 *
 * The turn is done by oscillating each ring's width, not by spinning it. A ring that narrows to
 * a line and opens again is a ring rotating about its own axis, which buys real dimensionality
 * from a flat ellipse.
 */
const RINGS: Array<{ rx: number; ry: number; tilt: number; dur: number; delay: number; w: number; o: number }> = [
  { rx: 40, ry: 40, tilt: 0, dur: 11, delay: -1.2, w: 1.1, o: 0.9 },
  { rx: 38, ry: 33, tilt: 58, dur: 9, delay: -4.4, w: 1, o: 0.75 },
  { rx: 41, ry: 27, tilt: 118, dur: 13, delay: -7.1, w: 0.9, o: 0.65 },
  { rx: 34, ry: 38, tilt: 26, dur: 10, delay: -2.6, w: 0.8, o: 0.55 },
  { rx: 43, ry: 21, tilt: 152, dur: 15, delay: -9.3, w: 0.8, o: 0.45 },
]

/** The nucleus: a handful of shards on their own small orbit, read as cubes by their facets. */
const SHARDS: Array<{ x: number; y: number; s: number; o: number }> = [
  { x: 0, y: -5, s: 4.6, o: 1 },
  { x: 5.5, y: -1, s: 3.8, o: 0.85 },
  { x: -5, y: 0.5, s: 4.2, o: 0.9 },
  { x: 1.5, y: 4.5, s: 3.4, o: 0.75 },
  { x: -2.5, y: -8, s: 2.6, o: 0.6 },
  { x: 7, y: 5, s: 2.4, o: 0.55 },
  { x: -7.5, y: 5.5, s: 2.8, o: 0.65 },
]

export function InterviewerCore({ size = 152 }: { size?: number }) {
  return (
    <svg
      viewBox="0 0 100 100"
      className="relative overflow-visible"
      style={{ width: size, height: size }}
    >
      <defs>
        <radialGradient id="core-halo">
          <stop offset="0%" stopColor={CORE} stopOpacity="0.55" />
          <stop offset="55%" stopColor={CORE} stopOpacity="0.14" />
          <stop offset="100%" stopColor={CORE} stopOpacity="0" />
        </radialGradient>
        <linearGradient id="core-shard" x1="0" y1="0" x2="0.6" y2="1">
          <stop offset="0%" stopColor="#dfe4ff" />
          <stop offset="55%" stopColor={CORE} />
          <stop offset="100%" stopColor={INDIGO} />
        </linearGradient>
      </defs>

      {/* Ambient field. Sits behind everything so the cage looks lit from within. */}
      <circle className="core-glow" cx="50" cy="50" r="46" fill="url(#core-halo)" />

      {RINGS.map((ring, i) => (
        <g key={i} transform={`rotate(${ring.tilt} 50 50)`}>
          <ellipse
            className="core-ring"
            cx="50"
            cy="50"
            rx={ring.rx}
            ry={ring.ry}
            fill="none"
            stroke={i % 2 === 0 ? SKY : CORE}
            strokeWidth={ring.w}
            opacity={ring.o}
            style={{ animationDuration: `${ring.dur}s`, animationDelay: `${ring.delay}s` }}
          />
        </g>
      ))}

      {/* The nucleus, counter-turning against the cage on its own slow clock. */}
      <g className="core-nucleus">
        {SHARDS.map((shard, i) => (
          <rect
            key={i}
            x={50 + shard.x - shard.s / 2}
            y={50 + shard.y - shard.s / 2}
            width={shard.s}
            height={shard.s}
            rx={0.6}
            fill="url(#core-shard)"
            opacity={shard.o}
            transform={`rotate(45 ${50 + shard.x} ${50 + shard.y})`}
          />
        ))}
      </g>

      {/* The bright centre the shards are suspended around. */}
      <circle className="core-glow" cx="50" cy="50" r="3.4" fill="#eef0ff" />
    </svg>
  )
}

/** Shared chrome for the three floating panels: frosted, hairline-edged, lifted off the scene. */
function Panel({
  children,
  className = "",
  style,
  delay = 0,
}: {
  children: React.ReactNode
  className?: string
  style?: React.CSSProperties
  delay?: number
}) {
  return (
    <div className={`absolute ${className}`} style={style}>
      <div className="hud-drift" style={{ animationDelay: `${delay}s` }}>
        <div
          className="rounded-[15px] p-4 backdrop-blur-md"
          style={{
            background: "linear-gradient(150deg, rgba(254,252,253,0.11), rgba(254,252,253,0.04))",
            boxShadow: `0 0 0 1px rgba(191,205,224,0.18), 0 22px 44px -20px rgba(0,0,0,0.9), inset 0 1px 0 rgba(254,252,253,0.14)`,
          }}
        >
          {children}
        </div>
      </div>
    </div>
  )
}

/** Panel 1: what the candidate is saying, and what the evaluator is marking as it arrives. */
function TranscriptPanel() {
  const bars: Array<{ w: number; c: string }> = [
    { w: 100, c: SKY },
    { w: 74, c: CYAN },
    { w: 88, c: VIOLET },
    { w: 56, c: GRAPE },
    { w: 92, c: SKY },
    { w: 66, c: CYAN },
  ]

  return (
    <Panel
      className="left-0 top-0 w-[228px]"
      style={{ transform: "translate3d(0,0,84px) rotateY(11deg)" }}
      delay={0}
    >
      <div className="mb-3 flex items-center justify-between">
        <span
          className="text-[10px] font-medium uppercase"
          style={{ color: SKY, letterSpacing: "0.18em", opacity: 0.75 }}
        >
          Transcript
        </span>
        <span
          className="rounded-full px-2 py-[3px] text-[9px] font-medium uppercase"
          style={{ background: "rgba(110,231,240,0.16)", color: CYAN, letterSpacing: "0.14em" }}
        >
          Match
        </span>
      </div>

      <div className="flex flex-col gap-[8px]">
        {bars.map((bar, i) => (
          <span
            key={i}
            className="hud-scan-line block h-[5px] rounded-full"
            style={{
              width: `${bar.w}%`,
              background: `linear-gradient(90deg, ${bar.c}, rgba(191,205,224,0.08))`,
              boxShadow: `0 0 10px -1px ${bar.c}`,
              animationDelay: `${i * 0.26}s`,
            }}
          />
        ))}
      </div>
    </Panel>
  )
}

/** Panel 2: the voice channel, live. */
function WaveformPill() {
  // A fixed, irregular set of heights rather than random ones: the bars must be identical on
  // every render, or the pill flickers whenever React re-renders the hero.
  const heights = [9, 17, 26, 15, 32, 22, 36, 25, 14, 30, 19, 33, 16, 24, 10, 27, 18, 12]

  return (
    <div
      className="absolute left-0 top-0 w-[292px]"
      style={{ transform: "translate3d(0,0,132px)" }}
    >
      <div className="hud-drift" style={{ animationDelay: "1.4s" }}>
        <div
          className="flex items-center gap-3 rounded-full px-4 py-2.5 backdrop-blur-md"
          style={{
            background: "linear-gradient(150deg, rgba(254,252,253,0.13), rgba(254,252,253,0.05))",
            boxShadow: `0 0 0 1px rgba(191,205,224,0.2), 0 20px 40px -18px rgba(0,0,0,0.9), inset 0 1px 0 rgba(254,252,253,0.16)`,
          }}
        >
          <span
            className="shrink-0 rounded-full px-2 py-[3px] text-[9px] font-medium uppercase"
            style={{ background: CYAN, color: "#04161a", letterSpacing: "0.14em" }}
          >
            Live
          </span>

          <svg viewBox="0 0 220 40" className="h-[34px] flex-1" preserveAspectRatio="none">
            {heights.map((h, i) => (
              <rect
                key={i}
                className="hud-wave-bar"
                x={i * 12 + 3}
                y={20 - h / 2}
                width="5"
                height={h}
                rx="2.5"
                fill={i % 3 === 0 ? CYAN : SKY}
                opacity={i % 3 === 0 ? 0.95 : 0.6}
                style={{ animationDelay: `${(i % 6) * 0.13}s`, transformOrigin: `${i * 12 + 5.5}px 20px` }}
              />
            ))}
          </svg>
        </div>
      </div>
    </div>
  )
}

/** Panel 3: how far one requirement has been established. */
function RadialPanel() {
  const R = 30
  const CIRC = 2 * Math.PI * R
  const PROGRESS = 0.94

  return (
    <Panel
      className="left-0 top-0 w-[188px]"
      style={{ transform: "translate3d(0,0,92px) rotateY(-11deg)" }}
      delay={0.7}
    >
      <span
        className="mb-2.5 block text-center text-[10px] font-medium uppercase"
        style={{ color: SKY, letterSpacing: "0.18em", opacity: 0.75 }}
      >
        Competency
      </span>

      <div className="relative mx-auto h-[98px] w-[98px]">
        <svg viewBox="0 0 76 76" className="h-full w-full -rotate-90">
          <circle cx="38" cy="38" r={R} fill="none" stroke="rgba(191,205,224,0.14)" strokeWidth="7.5" />
          <circle
            className="hud-arc"
            cx="38"
            cy="38"
            r={R}
            fill="none"
            stroke={CYAN}
            strokeWidth="7.5"
            strokeLinecap="round"
            style={
              {
                "--arc-length": `${CIRC}`,
                "--arc-offset": `${CIRC * (1 - PROGRESS)}`,
                filter: `drop-shadow(0 0 8px ${CYAN})`,
              } as React.CSSProperties
            }
          />
        </svg>
        <span
          className="absolute inset-0 flex items-center justify-center text-[22px] font-semibold"
          style={{ color: "#fefcfd" }}
        >
          94%
        </span>
      </div>

      <span
        className="mt-2.5 block rounded-full py-[4px] text-center text-[10px] font-medium"
        style={{ background: "rgba(59,51,85,0.75)", color: SKY }}
      >
        System Design
      </span>
    </Panel>
  )
}

