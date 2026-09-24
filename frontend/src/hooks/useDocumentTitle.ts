import { useEffect } from "react"

const SITE_NAME = "InterMind"

/**
 * Set the document title for a route.
 *
 * Every route rendered the same static "InterMind", which fails WCAG 2.4.2 (Page Titled, Level
 * A): the title is the first thing a screen reader announces on navigation and the only label a
 * browser tab, a bookmark or the history list has to distinguish one page from another. A
 * single-page app has to set it per route, because the server never sends a new document.
 *
 * Deliberately a six-line hook rather than a helmet library - this is the whole requirement,
 * and a dependency for it would be the larger cost.
 *
 * Pass `null` while a page's real title is still loading, to leave the previous title in place
 * rather than flashing a wrong one.
 */
export function useDocumentTitle(title: string | null): void {
  useEffect(() => {
    if (title === null) return
    const previous = document.title
    document.title = title === SITE_NAME ? title : `${title} · ${SITE_NAME}`
    return () => {
      document.title = previous
    }
  }, [title])
}
