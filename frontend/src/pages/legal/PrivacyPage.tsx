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
      <p>When the OpenAI integration is enabled, job descriptions and interview content are sent to OpenAI to generate questions, evaluate answers and write report narratives. AI evaluations can be wrong. Scores are calculated by application rules from the evaluated evidence, and they are not hiring decisions.</p>
      <p>Voice input is optional and typing always works. When it is used, the browser sends audio straight to Microsoft Azure AI Speech for transcription, and InterMind stores the resulting text rather than the audio.</p>
      <p>Provider regions, retention and data-processing agreements depend on the deployment and are not established here.</p>
    </LegalSection>

    <LegalSection title="Storage and access">
      <p>By default the project runs in memory and loses its data when the server stops. Configured with PostgreSQL, the same data survives a restart. There is no retention schedule, backup policy or deletion timetable.</p>
      <p>Recruiters see only their own workspace. A candidate's link opens one interview and never the evaluations or reports behind it, so keep interview links private.</p>
      <p>Passwords are stored only as hashes and every request is checked on the server. Hosting security, encryption and operational access still depend on the deployment.</p>
    </LegalSection>

    <LegalSection title="Other services and browser storage">
      <p>Typefaces load from Google Fonts, so a page load makes an ordinary browser request to Google. There is no analytics, advertising, tracking pixel or session-recording service in the application.</p>
      <p>One cookie keeps a recruiter signed in, and browser session storage holds a candidate's interview token, both described under <LegalLink to="/legal/cookies">Cookies</LegalLink>.</p>
      <p>Application logs record operational metadata rather than answer text. Host and provider logs are separate and not described here.</p>
    </LegalSection>

    <LegalSection title="Questions about your data">
      <p>Depending on where you are, you may have rights to access, correct or delete information held about you. This project publishes no request process or response time. If you were invited to an interview, the recruiter who sent the link decides how your answers are used, so ask them first.</p>
    </LegalSection>
  </LegalPage>
}
