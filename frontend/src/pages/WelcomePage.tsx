import { useLayoutEffect } from "react"
import { Link } from "react-router-dom"
import { ArrowDown, ArrowRight } from "lucide-react"
import { IntroSplash } from "../site/IntroSplash"
import { useLandingIntro } from "../site/journey/useLandingIntro"
import { SiteNav } from "../site/SiteNav"
import { NightAtmosphere } from "../components/ui/NightAtmosphere"
import { Marquee } from "../site/Marquee"
import { ProcessStage } from "../site/ProcessStage"
import { EvidenceChain } from "../site/EvidenceChain"
import { InteractiveHero3D } from "../site/InteractiveHero3D"
import { ScrollMeter } from "../components/layout/ScrollMeter"
import { Logo } from "../brand/Logo"
import { useDocumentTitle } from "../hooks/useDocumentTitle"
import "../site/landing.css"

const primary = "inline-flex min-h-[48px] items-center justify-center gap-2 rounded-full bg-fg px-7 py-3.5 text-sm font-medium text-canvas transition-colors hover:bg-accent"
const secondary = "inline-flex min-h-[48px] items-center justify-center gap-2 rounded-full border border-hair-strong px-7 py-3.5 text-sm font-medium text-fg transition-colors hover:bg-fg/5"

export function WelcomePage() {
  useDocumentTitle("InterMind")
  const intro = useLandingIntro()
  useLayoutEffect(() => {
    if (!window.location.hash || window.scrollY !== 0) return
    try { document.getElementById(decodeURIComponent(window.location.hash.slice(1)))?.scrollIntoView({ block: "start", behavior: "instant" }) } catch { /* Malformed hashes leave normal navigation available. */ }
  }, [])
  return <div className="night-room landing-restored relative min-h-screen" data-intro={intro.phase}>
    <IntroSplash phase={intro.phase} onSkip={intro.finish} />
    <NightAtmosphere />
    <ScrollMeter />
    <a className="sr-only left-4 top-4 z-50 rounded-full bg-fg font-medium text-canvas focus:not-sr-only focus:absolute focus:px-5 focus:py-3" href="#main">Skip to content</a>
    <SiteNav />
    <main id="main" tabIndex={-1}>
      <section className="landing-hero relative mx-auto w-full max-w-[86rem] px-5 pb-16 pt-24 sm:px-8 sm:pb-24">
        <div className="grid grid-cols-1 items-start gap-10 lg:grid-cols-[minmax(0,6fr)_minmax(0,7fr)] lg:gap-14">
          <div className="hero-copy flex flex-col items-start lg:pt-8">
            <div className="flex w-full items-center gap-4"><span className="type-meta shrink-0 text-accent">Autonomous interviewing</span><span className="h-px flex-1 bg-hair" /></div>
            <h1 className="type-hero mt-7 max-w-[19ch] text-balance text-fg">Every candidate gets a different interview.</h1>
            <p className="type-body mt-6 text-fg-soft">InterMind reads a job description, runs the interview on its own, and chooses each question based on how the candidate answered the last one. You get a clear write-up of what they showed, not just a transcript.</p>
            <div className="hero-actions mt-9 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
              <Link to="/signup" className={primary}>Create your workspace <ArrowRight size={17} aria-hidden="true" /></Link>
              <Link to="/login" className={`hero-signin ${secondary}`}>Recruiter sign in</Link>
              <a href="#how-it-works" className={secondary}>See how it works <ArrowDown size={16} aria-hidden="true" /></a>
            </div>
          </div>
          <div className="hero-visual relative flex h-[540px] w-full items-center justify-center lg:h-[600px]">
            <InteractiveHero3D phase={intro.phase} className="h-full w-full" />
          </div>
        </div>
      </section>
      <div className="process-band border-y border-hair bg-fg/[.03] py-4"><Marquee items={["Read the role", "Plan the interview", "Ask a question", "Listen to the answer", "Decide what comes next", "Ask for more if needed", "Score what was shown", "Write the report"]} duration={72} separator="→" itemClassName="type-sub text-fg" /></div>
      <section className="landing-problem mx-auto max-w-[86rem] px-5 py-20 sm:px-8 sm:py-28">
        <div className="grid grid-cols-1 gap-10 border-t border-hair pt-12 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)] lg:gap-16">
          <h2 className="type-section max-w-[16ch] text-balance text-fg">Most interviews ask everyone the same questions.</h2>
          <div className="flex flex-col gap-5"><p className="type-body text-fg-soft">A fixed list cannot tell the difference between someone who has done the work and someone who can describe it. It asks the strong candidate about things they already covered, and lets a vague answer through because nobody thought to push on it.</p><p className="type-body text-fg-soft">InterMind reads each answer before choosing the next question. Two people applying for the same job will not get the same interview, because what gets asked second depends on what was said first.</p></div>
        </div>
      </section>
      <div className="process-section border-y border-hair bg-fg/[.02] py-20 sm:py-28"><ProcessStage /></div>
      <section id="results" className="landing-results mx-auto max-w-[86rem] scroll-mt-24 px-5 py-20 sm:px-8 sm:py-28">
        <div className="grain-static plane-raised relative overflow-hidden px-6 py-14 sm:px-12 sm:py-20">
          <span aria-hidden="true" className="veil-deep" />
          <div className="relative grid grid-cols-1 gap-12 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)] lg:gap-16">
            <div className="results-heading self-start lg:sticky lg:top-28"><span className="type-meta text-accent">What you get at the end</span><h2 className="type-section mt-6 max-w-[17ch] text-balance text-fg">Every score points back to something the candidate said.</h2><p className="mt-6 max-w-sm text-lg leading-relaxed text-fg-soft">The report is not a summary of an impression. InterMind follows one requirement at a time, from the job description through to the answer that showed it, so you can see why a judgement was made and check it yourself.</p></div>
            <EvidenceChain />
          </div>
        </div>
      </section>
      <section className="landing-close mx-auto max-w-[86rem] px-5 pb-24 sm:px-8 sm:pb-32"><div className="flex flex-col items-start gap-8 border-t border-hair pt-14"><h2 className="type-section max-w-[18ch] text-fg">Give it a role. It runs the interview.</h2><p className="type-body text-fg-soft">Paste a job description, send the candidate a link, and read the write-up when they are done.</p><Link to="/signup" className={primary}>Create your workspace <ArrowRight size={17} aria-hidden="true" /></Link></div></section>
    </main>
      <footer className="border-t border-hair bg-fg/[0.02]">
        <div className="mx-auto max-w-[86rem] px-5 py-12 sm:px-8">
          <div className="flex flex-col gap-8 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex flex-col gap-4">
              <Logo size={24} tone="onDark" />
              <p className="max-w-sm text-sm leading-relaxed text-fg-soft">
                AI built to conduct the interview, evaluate the depth, and report the truth.
              </p>
            </div>

            <nav aria-label="Footer" className="flex flex-col gap-6 sm:flex-row sm:gap-14">
              <div className="flex flex-col gap-3 text-sm">
                <a
                  href="#how-it-works"
                  className="inline-flex min-h-[44px] items-center text-fg-muted transition-colors hover:text-fg"
                >
                  How it works
                </a>
                <a
                  href="#results"
                  className="inline-flex min-h-[44px] items-center text-fg-muted transition-colors hover:text-fg"
                >
                  What you get
                </a>
              </div>

              <div className="flex flex-col gap-3 text-sm">
                <Link
                  to="/legal/privacy"
                  className="inline-flex min-h-[44px] items-center text-fg-muted transition-colors hover:text-fg"
                >
                  Privacy
                </Link>
                <Link
                  to="/legal/terms"
                  className="inline-flex min-h-[44px] items-center text-fg-muted transition-colors hover:text-fg"
                >
                  Terms
                </Link>
                <Link
                  to="/legal/cookies"
                  className="inline-flex min-h-[44px] items-center text-fg-muted transition-colors hover:text-fg"
                >
                  Cookies
                </Link>
              </div>
            </nav>
          </div>

          <div className="mt-10 flex flex-col gap-4 border-t border-hair pt-6 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-fg-soft">
              Built by <span className="font-medium text-fg">Aliyah Alabdali</span>
            </p>

            {/* Provenance stays accurate and available without becoming a block of footer copy.
                Collapsed by default; native disclosure, so it is keyboard reachable. */}
            <details className="group text-sm">
              <summary className="inline-flex min-h-[44px] cursor-pointer list-none items-center text-fg-muted transition-colors hover:text-fg">
                Method and data sources
              </summary>
              <p className="mt-2 max-w-md text-sm leading-relaxed text-fg-soft">
                Role understanding is grounded in the job description you provide, alongside
                occupational data from O*NET 31.0, published by the U.S. Department of Labor.
                Scoring is computed from the interview itself, not generated as prose. The laptop above is a 3D model by{" "}
                <a href="https://sketchfab.com/3d-models/realistic-3d-laptop-model-high-quality-design-920fe8eceaf748a5b9ddd53385519322" target="_blank" rel="noreferrer noopener" className="underline decoration-hair-strong underline-offset-2 transition-colors hover:text-fg">Taohid Animation</a>, used under CC BY 4.0.
              </p>
            </details>
          </div>
        </div>
      </footer>
  </div>
}
