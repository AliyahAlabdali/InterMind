interface NightAtmosphereProps {
  /**
   * `fixed` for a page that scrolls - the atmosphere stays put while content moves over it.
   * `absolute` for a contained panel, where it should scroll with its own box.
   */
  position?: "fixed" | "absolute"
}

/**
 * The interview room's environment, available to any page.
 *
 * This is the same construction as the stage's own background, value for value: obsidian, a
 * space-indigo field breaking the dark from the top-left, a dusty-grape field from the
 * bottom-right, and grain at half strength over both. Those two fields are the "purple and soft
 * light blue shadows" the room is built from - they are what keeps a near-black page reading as
 * a lit space rather than a flat rectangle.
 *
 * Deliberately a copy of the recipe rather than a shared import with the stage: the interview
 * room is the product's reference implementation and must not acquire a dependency that a later
 * change to a marketing page could disturb. The values are identical on purpose, and if one
 * moves the other should move with it.
 *
 * Cost: two elements on one long transform loop (stilled under reduced motion by `.atmo-field`'s
 * own rule) plus one static grain layer. Nothing reads scroll position; nothing animates a
 * paint property.
 */
export function NightAtmosphere({ position = "fixed" }: NightAtmosphereProps) {
  return (
    <div
      aria-hidden="true"
      className={`pointer-events-none ${position} inset-0 -z-10 overflow-hidden`}
    >
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

      {/* Grain at a lower opacity than a light page's: on a dark field the same value reads as
          noise in the image rather than as texture in the surface. */}
      <div className="grain-static absolute inset-0 opacity-50" />
    </div>
  )
}
