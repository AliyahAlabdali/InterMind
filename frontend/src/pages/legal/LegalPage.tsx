import { useLayoutEffect, type ReactNode } from "react"
import { Link, NavLink, useLocation, useNavigationType } from "react-router-dom"
import { ArrowLeft, ArrowUpRight } from "lucide-react"
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
 * How to reach the person who maintains this.
 *
 * Kept separate from the repository link below on purpose. One is the author, the other is the
 * code, and a single "GitHub" link cannot be both without losing whichever the reader wanted.
 */
const MAINTAINER: Array<{ label: string; href: string; name: string }> = [
  { label: "GitHub", href: "https://github.com/AliyahAlabdali", name: "Aliyah Alabdali on GitHub" },
  { label: "LinkedIn", href: "https://www.linkedin.com/in/aliyah-alabdali-5ba599274/", name: "Aliyah Alabdali on LinkedIn" },
  { label: "Portfolio", href: "https://aliyahalabdali.github.io", name: "Aliyah Alabdali's portfolio" },
  { label: "Email", href: "mailto:AliyahAlabdali24@gmail.com", name: "Email Aliyah Alabdali" },
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
            {MAINTAINER.map(({ label, href, name }) => {
              const external = !href.startsWith("mailto:")
              return <li key={label}>
                <a href={href} aria-label={name} {...(external ? { target: "_blank", rel: "noreferrer noopener" } : {})}>{label}</a>
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
