/**
 * The room the interview happens in.
 *
 * The same construction as the site's `Atmosphere` - two soft drifting fields and a static
 * grain overlay - inverted onto near-black. It exists so the stage reads as a lit space with
 * depth rather than a flat black rectangle, and so the interviewer looks like it is standing in
 * something.
 *
 * Nothing here reads scroll position and nothing animates a paint property: the two fields move
 * on the shared long `transform` loop (stilled entirely under reduced motion by `.atmo-field`'s
 * own rule), which keeps the whole background on the compositor while a WebGL canvas and a live
 * microphone are already running.
 */
export function StageAtmosphere() {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10 overflow-hidden">
      <div className="absolute inset-0 bg-black" />

      <span
        className="atmo-field left-[-12%] top-[-16%] h-[62vw] w-[62vw] opacity-70"
        style={{
          background: "radial-gradient(circle, rgba(59,51,85,0.85) 0%, rgba(59,51,85,0) 70%)",
        }}
      />
      <span
        className="atmo-field bottom-[-24%] right-[-18%] h-[52vw] w-[52vw] opacity-60"
        style={{
          animationDelay: "-22s",
          background: "radial-gradient(circle, rgba(93,93,129,0.55) 0%, rgba(93,93,129,0) 70%)",
        }}
      />

      {/* Grain at a lower opacity than the site's: on a dark field the same value reads as
          noise in the image rather than as texture in the surface. */}
      <div className="grain-static absolute inset-0 opacity-50" />
    </div>
  )
}
