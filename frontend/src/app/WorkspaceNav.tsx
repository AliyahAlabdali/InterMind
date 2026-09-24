import { useState } from "react"
import { Link, NavLink, useNavigate } from "react-router-dom"
import { AnimatePresence, motion } from "motion/react"
import { Menu, Plus, X, LogOut } from "lucide-react"
import { Logo } from "../brand/Logo"
import { transition } from "../design/motion"
import { recruiterLogout } from "../api/auth"

const LINKS = [
  { to: "/interviews", label: "Interviews" },
  { to: "/candidates", label: "Candidates" },
]

/**
 * The workspace's only navigation: a compact top bar, persistent across the product.
 *
 * Still no sidebar. A rail for two destinations would spend a fifth of the screen restating an
 * information architecture this small, and a permanent left rail is the single strongest signal
 * that a product is an admin panel. The bar stays out of the way and the page below it does the
 * work of saying where you are.
 */
export function WorkspaceNav({ onDark = false }: { onDark?: boolean }) {
  const navigate = useNavigate()
  const [menuOpen, setMenuOpen] = useState(false)

  return (
    <header className="sticky top-0 z-30 border-b border-hair bg-canvas/90 backdrop-blur-md">
      <div className="shell flex items-center justify-between gap-6 py-3">
        <div className="flex items-center gap-8">
          <Link
            to="/interviews"
            aria-label="InterMind"
            className="inline-flex min-h-[44px] shrink-0 items-center"
          >
            <Logo size={24} animated tone={onDark ? "onDark" : "onLight"} />
          </Link>

          <nav className="hidden items-center gap-7 sm:flex" aria-label="Workspace">
            {LINKS.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                className={({ isActive }) =>
                  `relative inline-flex min-h-[44px] items-center text-sm transition-colors duration-200 ${
                    isActive ? "text-fg" : "text-fg-muted hover:text-fg"
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    {link.label}
                    {/* The marker slides between links rather than cutting, so the navigation
                        itself shows the move you just made. */}
                    {isActive && (
                      <motion.span
                        layoutId="workspace-nav-active"
                        className="absolute inset-x-0 -bottom-[13px] h-[2px] rounded-full bg-fg"
                        transition={transition.state}
                      />
                    )}
                  </>
                )}
              </NavLink>
            ))}
          </nav>
        </div>

        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => navigate("/interviews/new")}
            className="inline-flex min-h-[44px] items-center gap-1.5 rounded-full bg-fg px-4 text-sm font-medium text-canvas transition-colors duration-200 hover:bg-accent"
          >
            <Plus size={15} strokeWidth={2.2} aria-hidden="true" />
            <span className="hidden sm:inline">New interview</span>
            <span className="sm:hidden">New</span>
          </button>

          {/* Signs out server-side, then reloads so the workspace re-checks its session and
              falls back to the sign-in gate. Revoking on the server is the part that matters -
              clearing the cookie alone would leave a live session behind. */}
          <button
            type="button"
            onClick={async () => {
              try {
                await recruiterLogout()
              } finally {
                window.location.assign("/interviews")
              }
            }}
            className="hidden min-h-[44px] items-center gap-1.5 rounded-full px-3 text-sm text-fg-muted transition-colors duration-200 hover:bg-fg/[0.06] hover:text-fg sm:inline-flex"
          >
            <LogOut size={15} aria-hidden="true" />
            Sign out
          </button>

          <button
            type="button"
            aria-label={menuOpen ? "Close menu" : "Open menu"}
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((open) => !open)}
            className="inline-flex h-11 w-11 items-center justify-center rounded-full text-fg-muted transition-colors hover:bg-fg/[0.06] hover:text-fg sm:hidden"
          >
            {menuOpen ? <X size={18} aria-hidden="true" /> : <Menu size={18} aria-hidden="true" />}
          </button>
        </div>
      </div>

      <AnimatePresence>
        {menuOpen && (
          <motion.nav
            aria-label="Workspace"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={transition.state}
            className="overflow-hidden border-t border-hair sm:hidden"
          >
            <div className="shell flex flex-col py-1">
              {LINKS.map((link) => (
                <NavLink
                  key={link.to}
                  to={link.to}
                  onClick={() => setMenuOpen(false)}
                  className={({ isActive }) =>
                    `flex min-h-[48px] items-center text-sm ${
                      isActive ? "font-medium text-fg" : "text-fg-muted"
                    }`
                  }
                >
                  {link.label}
                </NavLink>
              ))}
            </div>
          </motion.nav>
        )}
      </AnimatePresence>
    </header>
  )
}
