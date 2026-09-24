import { useRef, useState } from "react"
import { Link } from "react-router-dom"
import { ArrowUpRight, Menu, X } from "lucide-react"
import { Logo } from "../brand/Logo"

const SECTIONS = [
  { href: "#how-it-works", label: "How it works" },
  { href: "#results", label: "What you get" },
]

/** Public site navigation (brief §5): minimal, top-aligned, no sidebar. */
export function SiteNav() {
  const [open, setOpen] = useState(false)
  const toggle = useRef<HTMLButtonElement>(null)

  return (
    <header onKeyDown={event => { if (event.key === "Escape" && open) { setOpen(false); toggle.current?.focus() } }} className="landing-nav fixed inset-x-0 top-0 z-40 border-b border-hair bg-canvas/85 backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-6 px-5 py-4 sm:px-8">
        <Link to="/" aria-label="InterMind" className="inline-flex min-h-[44px] items-center">
          <Logo size={26} animated tone="onDark" />
        </Link>

        <nav className="hidden items-center gap-9 md:flex" aria-label="Site">
          {SECTIONS.map((section) => (
            <a
              key={section.href}
              href={section.href}
              className="inline-flex min-h-[44px] items-center text-sm text-fg-muted transition-colors hover:text-fg"
            >
              {section.label}
            </a>
          ))}
        </nav>

        <div className="flex items-center gap-2">
          {/* Points at sign-in, not at the workspace: a visitor clicking this is told what it
              is before being asked for credentials, instead of being bounced off a gate. */}
          <Link
            to="/login"
            className="inline-flex min-h-[44px] items-center gap-1 rounded-full bg-fg px-5 py-2.5 text-sm font-medium text-canvas transition-colors duration-200 hover:bg-accent"
          >
            Sign in
            <ArrowUpRight size={15} aria-hidden="true" />
          </Link>
          <button
            ref={toggle}
            type="button"
            aria-label={open ? "Close menu" : "Open menu"}
            aria-expanded={open}
            aria-controls="landing-mobile-nav"
            onClick={() => setOpen((value) => !value)}
            className="inline-flex h-11 w-11 items-center justify-center rounded-full text-fg-muted transition-colors hover:bg-fg/10 hover:text-fg md:hidden"
          >
            {open ? <X size={18} aria-hidden="true" /> : <Menu size={18} aria-hidden="true" />}
          </button>
        </div>
      </div>

        {open && (
          <nav
            id="landing-mobile-nav"
            aria-label="Mobile site"
            className="border-t border-hair bg-canvas md:hidden"
          >
            <div className="flex flex-col px-5 py-3">
              {SECTIONS.map((section) => (
                <a
                  key={section.href}
                  href={section.href}
                  onClick={() => setOpen(false)}
                  className="flex min-h-[44px] items-center text-fg-muted"
                >
                  {section.label}
                </a>
              ))}
            </div>
          </nav>
        )}
    </header>
  )
}
