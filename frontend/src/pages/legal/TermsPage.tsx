import { LegalLink, LegalPage, LegalSection } from "./LegalPage"

export function TermsPage() {
  return <LegalPage title="Terms" intro="What this project does, what its output is worth, and where its limits are.">
    <LegalSection title="What InterMind does">
      <p>InterMind reads a job description, plans an interview, asks questions and follow-ups based on how the candidate answered, and produces a report that points back to what was said. Candidates can type, or use optional speech transcription.</p>
    </LegalSection>

    <LegalSection title="Use the output with judgment">
      <p>AI evaluations may be incomplete, inconsistent or wrong. A report combines evaluated evidence, calculated scores and an AI-written narrative. It does not make a hiring decision and should not be the only basis for one.</p>
      <p>No accuracy rate has been validated and no fairness certification exists. InterMind does not verify who a candidate is, run background checks, or detect impersonation or cheating.</p>
    </LegalSection>

    <LegalSection title="Responsible use">
      <ul>
        <li>Use only information you are entitled to provide, and tell candidates that AI conducts and evaluates the interview.</li>
        <li>Read the evidence yourself rather than the score alone. Real recruitment use needs the notices and safeguards that apply where you are.</li>
        <li>Do not access another person's account, interview or report. Keep passwords and candidate invitation links private.</li>
      </ul>
    </LegalSection>

    <LegalSection title="Providers and limits">
      <p>Candidate answers are used to run and evaluate the interview. The application has no model-training pipeline of its own, and content sent to OpenAI or Azure Speech is also handled under those providers' terms. <LegalLink to="/legal/privacy">Privacy</LegalLink> has the current data flows.</p>
      <p>This is a personal project rather than a service, so there is no uptime or support commitment, and nothing here is a warranty or a commercial agreement. Those questions would need answering before anyone relied on it for real recruitment.</p>
    </LegalSection>
  </LegalPage>
}
