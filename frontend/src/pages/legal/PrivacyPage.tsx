import { LegalLink, LegalPage, LegalSection } from "./LegalPage"

export function PrivacyPage() {
  return <LegalPage title="Privacy" intro="What InterMind processes during an interview, which services see it, and where it is kept.">
    <LegalSection title="What InterMind processes">
      <ul>
        <li><strong>Recruiters:</strong> account email and a password hash, session information, job descriptions, and the role analysis and interview plans derived from them.</li>
        <li><strong>Candidates:</strong> the name the recruiter enters, and optionally an email used only as a label in that recruiter's workspace. InterMind does not send email.</li>
        <li><strong>Interviews:</strong> access tokens, questions, typed answers, evaluations, supporting quotations, scores, reports and activity records.</li>
      </ul>
      <p>All of it exists to run a role-specific interview and produce the recruiter's report. Avoid putting unrelated sensitive information into a job description or an answer.</p>
    </LegalSection>

    <LegalSection title="AI processing and optional voice">
      <p>InterMind uses the OpenAI API for live job analysis, interview planning, answer evaluation and report writing. Job descriptions, interview content and report inputs are sent to OpenAI for those purposes. AI evaluations can be wrong. Scores are calculated by application rules from the evaluated evidence, and they are not hiring decisions.</p>
      <p>Voice input is optional and typing always works. When it is used, the browser sends audio straight to Microsoft Azure AI Speech in East US for transcription, and InterMind stores the resulting text rather than the audio.</p>
      <p>OpenAI may process data under its own regional and retention arrangements. We cannot promise its processing stays in the database region or that deleting an InterMind record immediately deletes provider-held copies.</p>
    </LegalSection>

    <LegalSection title="Storage, regions and access">
      <p>The public backend and PostgreSQL database currently run on Microsoft Azure in UAE North. The frontend is hosted by Vercel, which can serve its static assets through a global network. A future move of the backend and database to Frankfurt is being prepared, but has not happened on this public site.</p>
      <p>Recruiters see only their own workspace. A candidate's link opens one interview and never the evaluations or reports behind it, so keep interview links private.</p>
      <p>Passwords are stored as hashes; recruiter sessions use an HttpOnly cookie, and access is checked on the server. Authorized hosting and database operators may have operational access. Cross-border processing can occur through Vercel, OpenAI, Azure Speech and their subprocessors.</p>
    </LegalSection>

    <LegalSection title="Retention and deletion">
      <p>The approved targets are to remove interview data, answers, evaluations and reports 90 days after the last accepted interview activity or report creation, and to retain encrypted backups under our control for no more than 30 days. These targets are <strong>not yet operating on the public deployment</strong>: the database migration, scheduled cleanup, backup controls and production verification are still pending. Provider-managed backup history may differ. We do not currently promise automatic deletion on those dates.</p>
      <p>Recruiter accounts and job descriptions have no automatic deletion timetable. You may request deletion; we will verify the request and explain any data that must be kept or cannot yet be removed from a provider or backup. Restoring a backup could reintroduce previously deleted records unless those requests are reapplied.</p>
    </LegalSection>

    <LegalSection title="Other services and browser storage">
      <p>Typefaces load from Google Fonts, so a page load makes an ordinary browser request to Google. There is no analytics, advertising, tracking pixel or session-recording service in the application.</p>
      <p>One cookie keeps a recruiter signed in, and browser session storage holds a candidate's interview token, both described under <LegalLink to="/legal/cookies">Cookies</LegalLink>.</p>
      <p>Application logs are intended to record operational metadata rather than answer text. Hosting and provider logs follow their own retention terms.</p>
    </LegalSection>

    <LegalSection title="Your choices and requests">
      <p>Depending on the law that applies to you, you may request access, correction, deletion or a copy of your information, or object to some processing. Contact <a href="mailto:AliyahAlabdali24@gmail.com">AliyahAlabdali24@gmail.com</a>. We will verify identity and the interview or account involved before disclosing or deleting data. No self-service candidate deletion or guaranteed response time is currently available.</p>
      <p>If a recruiter invited you, you may also contact them about how they use your answers. You can use typed answers without enabling voice input. Please avoid entering unrelated sensitive information.</p>
    </LegalSection>
  </LegalPage>
}
