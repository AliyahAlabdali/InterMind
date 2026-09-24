import type { AnchorHTMLAttributes, ButtonHTMLAttributes, ReactNode } from "react"

/**
 * Icon-only actions.
 *
 * The visible mark stays small - these sit at the end of dense rows and a row of 44px squares
 * would out-weigh the row's own content - but the *hit area* is a full 44px square, because a
 * 32px target is the single most common touch failure in a list UI.
 */
const BASE =
  "relative inline-flex h-11 w-11 items-center justify-center rounded-full text-fg-muted transition-colors duration-200 hover:bg-fg/[0.06] hover:text-fg"

/**
 * Anchored to the button's right edge rather than centred on it.
 *
 * These buttons sit at the end of a row, so a centred tooltip hangs past the container and
 * widens the document - which showed up as a real horizontal scrollbar on the candidates page
 * at tablet width. An absolutely positioned element still counts toward `scrollWidth` even at
 * zero opacity, so the fix has to be in where it sits, not in whether it is visible.
 */
function Tooltip({ label }: { label: string }) {
  return (
    <span
      role="tooltip"
      className="pointer-events-none absolute -top-7 right-0 z-10 hidden max-w-[14rem] truncate rounded-md bg-fg px-2 py-1 text-[11px] font-medium text-canvas opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100 sm:block"
    >
      {label}
    </span>
  )
}

interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  label: string
  icon: ReactNode
  tone?: "default" | "success"
}

export function IconButton({ label, icon, tone = "default", className = "", ...rest }: IconButtonProps) {
  return (
    <span className="group relative inline-flex">
      <button
        type="button"
        aria-label={label}
        className={`${BASE} ${tone === "success" ? "text-ok hover:text-ok" : ""} ${className}`}
        {...rest}
      >
        {icon}
      </button>
      <Tooltip label={label} />
    </span>
  )
}

interface IconLinkProps extends AnchorHTMLAttributes<HTMLAnchorElement> {
  label: string
  icon: ReactNode
}

export function IconLink({ label, icon, className = "", ...rest }: IconLinkProps) {
  return (
    <span className="group relative inline-flex">
      <a aria-label={label} className={`${BASE} ${className}`} {...rest}>
        {icon}
      </a>
      <Tooltip label={label} />
    </span>
  )
}
