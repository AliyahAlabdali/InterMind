interface LogoProps {
  size?: number
  withWordmark?: boolean
  className?: string
}

/**
 * Abstract InterMind mark: a charcoal tile holding a smooth periwinkle -> lavender ribbon,
 * echoing the product logo's conversational/profile motif without reproducing it outright.
 */
export function Logo({ size = 32, withWordmark = true, className = "" }: LogoProps) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <svg
        width={size}
        height={size}
        viewBox="0 0 32 32"
        fill="none"
        role="img"
        aria-label="InterMind"
      >
        <rect width="32" height="32" rx="9" fill="#1E2028" />
        <path
          d="M8 20.5c2.4 0 3-6.5 6-6.5 2.2 0 2.3 3.5 4.5 3.5 2.6 0 3-6 5.5-6"
          stroke="url(#intermind-ribbon)"
          strokeWidth="2.1"
          strokeLinecap="round"
          fill="none"
        />
        <circle cx="22.5" cy="10.5" r="1.6" fill="url(#intermind-ribbon)" />
        <defs>
          <linearGradient id="intermind-ribbon" x1="8" y1="20" x2="24" y2="9" gradientUnits="userSpaceOnUse">
            <stop stopColor="#6B7BE0" />
            <stop offset="1" stopColor="#A29BE8" />
          </linearGradient>
        </defs>
      </svg>
      {withWordmark && (
        <span
          className="text-[17px] font-semibold tracking-tight text-ink"
          style={{ fontFamily: "var(--font-display)" }}
        >
          InterMind
        </span>
      )}
    </span>
  )
}
