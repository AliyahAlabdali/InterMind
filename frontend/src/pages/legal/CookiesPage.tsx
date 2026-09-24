import { LegalLink, LegalPage, LegalSection } from "./LegalPage"

export function CookiesPage() {
  return <LegalPage title="Cookies" intro="Two pieces of browser storage, both of them for access. Nothing for advertising or analytics.">
    <LegalSection title="Recruiter sign-in">
      <p>The <code>intermind_recruiter_session</code> cookie holds an opaque session identifier and nothing else: no password, no interview content. It is set by recruiter signup or sign-in, never by opening a candidate link.</p>
      <p>It is HttpOnly and SameSite=Strict, and lasts eight hours by default, which a deployment can change. Signing out revokes the session on the server and clears the cookie.</p>
    </LegalSection>

    <LegalSection title="Candidate interview access">
      <p>A candidate's interview token is kept in <code>sessionStorage</code> under a key for that interview, so refreshing or moving between pages in the tab does not require the token to sit in every address.</p>
      <p>It is not a tracking mechanism. It opens one interview and never the recruiter's evaluations or reports, and how long the browser keeps it depends on that browser's session restoration.</p>
    </LegalSection>

    <LegalSection title="No tracking storage">
      <p>There is no analytics, advertising tag, tracking pixel, session recording or other non-essential storage in the application, which is why it shows no cookie-consent banner.</p>
    </LegalSection>

    <LegalSection title="Third-party connections">
      <p>Typefaces load from Google Fonts. If a candidate uses voice input, their browser connects to Microsoft Azure AI Speech once they start recording. Neither connection involves the sign-in cookie. <LegalLink to="/legal/privacy">Privacy</LegalLink> covers what reaches those providers.</p>
    </LegalSection>

    <LegalSection title="Clearing it">
      <p>Your browser can clear or block this site's storage at any time. Clearing the cookie signs a recruiter out; clearing session storage may mean a candidate has to reopen their original invitation link.</p>
    </LegalSection>
  </LegalPage>
}
