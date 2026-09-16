import type { ButtonHTMLAttributes, ReactNode } from "react"

type Variant = "primary" | "secondary" | "ghost"

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  isLoading?: boolean
  children: ReactNode
}

const VARIANT_CLASSES: Record<Variant, string> = {
  primary: "bg-ink text-white hover:bg-[#2b2e3a] disabled:bg-ink-muted",
  secondary:
    "bg-white text-ink border border-border hover:border-border-strong hover:bg-ivory-100 disabled:text-ink-muted",
  ghost: "bg-transparent text-ink-soft hover:bg-ivory-100 disabled:text-ink-muted",
}

export function Button({
  variant = "primary",
  isLoading = false,
  disabled,
  className = "",
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-[10px] px-5 py-2.5 text-sm font-medium transition-colors duration-150 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-periwinkle disabled:cursor-not-allowed ${VARIANT_CLASSES[variant]} ${className}`}
      disabled={disabled || isLoading}
      {...rest}
    >
      {isLoading && (
        <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
      )}
      {children}
    </button>
  )
}
