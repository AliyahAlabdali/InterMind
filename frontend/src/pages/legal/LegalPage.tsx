import { useLayoutEffect, type ReactNode } from "react"
import { Link, NavLink, useLocation, useNavigationType } from "react-router-dom"
import { ArrowLeft, ArrowUpRight, Globe, Mail } from "lucide-react"
import { Logo } from "../../brand/Logo"
import { NightAtmosphere } from "../../components/ui/NightAtmosphere"
import { useDocumentTitle } from "../../hooks/useDocumentTitle"
import "./legal.css"

/**
 * The shell all three information pages share.
 *
 * It carries everything that would otherwise be restated on each page: the notice about what
 * these pages are, and who maintains the project. Saying either of those three times is what
 * made the earlier drafts read as legal boilerplate rather than as an explanation.
 */

/**
 * The GitHub and LinkedIn marks, inlined.
 *
 * lucide-react dropped its brand glyphs in v1, and a generic icon cannot stand in for these two:
 * a git-branch or briefcase beside a profile link is a guess the reader has to decode, where the
 * real mark is read instantly. Inlined as single paths rather than pulled from a second icon
 * package, so the row costs no new dependency and no network request. `currentColor` is what
 * lets them inherit exactly the colour and hover treatment of the lucide icons beside them.
 */
const MARK = "0 0 24 24"

function GitHubMark() {
  return <svg width="18" height="18" viewBox={MARK} fill="currentColor" aria-hidden="true" focusable="false">
    <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12" />
  </svg>
}

function LinkedInMark() {
  return <svg width="18" height="18" viewBox={MARK} fill="currentColor" aria-hidden="true" focusable="false">
    <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.225 0z" />
  </svg>
}

/**
 * How to reach the person who maintains this.
 *
 * Kept separate from the repository link below on purpose. One is the author, the other is the
 * code, and a single "GitHub" link cannot be both without losing whichever the reader wanted.
 *
 * Shown as marks rather than words: four labels and three separator dots were more typography
 * than a row of destinations needs, and each mark is recognised faster than its own name. The
 * name each one carries lives in `aria-label`, so nothing is lost to a screen reader.
 */
const MAINTAINER: Array<{ label: string; href: string; name: string; icon: ReactNode }> = [
  { label: "GitHub", href: "https://github.com/AliyahAlabdali", name: "Aliyah Alabdali on GitHub", icon: <GitHubMark /> },
  { label: "LinkedIn", href: "https://www.linkedin.com/in/aliyah-alabdali-5ba599274/", name: "Aliyah Alabdali on LinkedIn", icon: <LinkedInMark /> },
  { label: "Portfolio", href: "https://aliyahalabdali.github.io", name: "Aliyah Alabdali's Portfolio", icon: <Globe size={18} aria-hidden="true" /> },
  { label: "Email", href: "mailto:AliyahAlabdali24@gmail.com", name: "Email Aliyah Alabdali", icon: <Mail size={18} aria-hidden="true" /> },
]

/** The project's own repository, which is not the maintainer's profile. */
const REPOSITORY = "https://github.com/AliyahAlabdali/InterMind"

/**
 * React Router keeps the document's scroll offset when changing pages. Reset before paint
 * for PUSH/REPLACE arrivals in this shared shell, covering sidebar, footer and body links.
 * Leave POP alone, including the initial render on a direct load or refresh, so native
 * Back/Forward and refresh restoration can keep their positions without global overrides.
 */
function useLegalScrollReset() {
  const { pathname } = useLocation()
  const navigationType = useNavigationType()

  useLayoutEffect(() => {
    if (navigationType === "POP") return

    window.scrollTo(0, 0)
  }, [pathname, navigationType])
}

export function LegalSection({ title, children }: { title: string; children: ReactNode }) {
  return <section className="legal-section"><h2>{title}</h2><div>{children}</div></section>
}

/**
 * A link from one of these pages to another.
 *
 * Router navigation rather than a bare `href`, so moving between them never reloads the
 * application and the text never resolves against whatever origin happens to be serving it.
 */
export function LegalLink({ to, children }: { to: string; children: ReactNode }) {
  return <Link to={to}>{children}</Link>
}

export function LegalPage({ title, intro, children }: { title: string; intro: string; children: ReactNode }) {
  useDocumentTitle(title)
  useLegalScrollReset()
  return <div className="night-room legal-page relative min-h-screen">
    <NightAtmosphere />
    <a href="#main" className="legal-skip">Skip to content</a>
    <header className="border-b border-hair"><div className="legal-header">
      <Link to="/" aria-label="InterMind home"><Logo size={24} tone="onDark" /></Link>
      <Link to="/" className="legal-back"><ArrowLeft size={15} aria-hidden="true" /> Back to InterMind</Link>
    </div></header>
    <div className="legal-layout">
      <aside><p className="type-meta text-fg-muted">Project information</p><nav aria-label="Legal pages">
        <NavLink to="/legal/privacy">Privacy</NavLink><NavLink to="/legal/terms">Terms</NavLink><NavLink to="/legal/cookies">Cookies</NavLink>
      </nav></aside>
      <main id="main" tabIndex={-1}>
        <h1>{title}</h1><p className="legal-intro">{intro}</p>
        {/* Honest about what these pages are without dressing it as a warning. They describe a
            working project accurately; they are not a reviewed policy for a live service, and
            saying so once, quietly, is the whole of it. */}
        <p className="legal-notice" role="note"><span>Project notice</span> These pages describe how InterMind works today. Running it as a live recruitment service would need further review.</p>
        {children}
        <section className="legal-contact" aria-labelledby="project-maintainer">
          <h2 id="project-maintainer">Project &amp; maintainer</h2>
          <p>InterMind is a personal AI engineering project created and maintained by Aliyah Alabdali.</p>
          <ul className="legal-links">
            {MAINTAINER.map(({ label, href, name, icon }) => {
              const external = !href.startsWith("mailto:")
              return <li key={label}>
                <a href={href} aria-label={name} {...(external ? { target: "_blank", rel: "noreferrer noopener" } : {})}>{icon}</a>
              </li>
            })}
          </ul>
          <a className="legal-repo" href={REPOSITORY} target="_blank" rel="noreferrer noopener">View InterMind on GitHub <ArrowUpRight size={14} aria-hidden="true" /></a>
          <p className="legal-contact-note">For anything involving candidate information, use email rather than a public GitHub issue.</p>
        </section>
      </main>
    </div>
    <footer className="legal-footer"><Link to="/">InterMind</Link><span>Built by Aliyah Alabdali</span></footer>
  </div>
}
