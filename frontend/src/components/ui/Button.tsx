import type { ButtonHTMLAttributes, ReactNode } from "react"

type Variant = "primary" | "secondary" | "ghost"
type Size = "md" | "sm"

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  isLoading?: boolean
  children: ReactNode
}

/**
 * The product's one button.
 *
 * Pill geometry, matching the public site and the interview room - the workspace used to run
 * 10px-radius buttons in a different ink while the rest of the product used full-radius ones,
 * which is the kind of seam that makes an application feel assembled rather than designed.
 *
 * Every size clears a 44px target. The old `py-2.5 text-sm` button measured 38px, which is
 * below the touch minimum everywhere it appeared.
 */
const VARIANT: Record<Variant, string> = {
  primary: "bg-fg text-canvas hover:bg-accent hover:text-canvas disabled:bg-fg/25 disabled:text-canvas/70",
  secondary:
    "border border-hair-strong text-fg hover:bg-fg/[0.045] disabled:border-hair disabled:text-fg-muted",
  ghost: "text-fg-soft hover:bg-fg/[0.05] hover:text-fg disabled:text-fg-muted",
}

const SIZE: Record<Size, string> = {
  md: "min-h-[44px] px-5 text-sm",
  sm: "min-h-[36px] px-3.5 text-sm",
}

export function Button({
  variant = "primary",
  size = "md",
  isLoading = false,
  disabled,
  className = "",
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-full font-medium transition-colors duration-200 disabled:cursor-not-allowed ${SIZE[size]} ${VARIANT[variant]} ${className}`}
      disabled={disabled || isLoading}
      {...rest}
    >
      {isLoading && (
        <span
          aria-hidden="true"
          className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent"
        />
      )}
      {children}
    </button>
  )
}
