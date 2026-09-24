import { Navigate, Route, Routes, useParams } from "react-router-dom"
import { WorkspaceLayout } from "./app/WorkspaceLayout"
import { RequireRecruiter } from "./app/RequireRecruiter"
import { RecruiterLoginPage } from "./pages/RecruiterLoginPage"
import { RecruiterSignupPage } from "./pages/RecruiterSignupPage"
import { CandidateLayout } from "./layouts/CandidateLayout"
import { WelcomePage } from "./pages/WelcomePage"
import { InterviewsPage } from "./pages/workspace/InterviewsPage"
import { NewInterviewPage } from "./pages/workspace/NewInterviewPage"
import { InterviewDetailPage } from "./pages/workspace/InterviewDetailPage"
import { CandidatesPage } from "./pages/workspace/CandidatesPage"
import { ReportPage } from "./pages/workspace/ReportPage"
import { CandidateLandingPage } from "./pages/candidate/CandidateLandingPage"
import { InterviewStagePage } from "./pages/candidate/InterviewStagePage"
import { CandidateCompletePage } from "./pages/candidate/CandidateCompletePage"
import { PrivacyPage } from "./pages/legal/PrivacyPage"
import { TermsPage } from "./pages/legal/TermsPage"
import { CookiesPage } from "./pages/legal/CookiesPage"

/** Recruiter-only. Unauthenticated visitors are redirected to sign-in, not shown a form here. */
function workspace(element: React.ReactNode) {
  return (
    <RequireRecruiter>
      <WorkspaceLayout>{element}</WorkspaceLayout>
    </RequireRecruiter>
  )
}

function candidate(element: React.ReactNode) {
  return <CandidateLayout>{element}</CandidateLayout>
}

/**
 * Old candidate links carried the question id in the URL. The server owns which question is
 * current, so the stage no longer needs one - but links already sent to candidates must keep
 * working, so they redirect instead of 404ing.
 */
function LegacyQuestionRedirect() {
  const { interviewId } = useParams<{ interviewId: string }>()
  return <Navigate to={`/candidate/interviews/${interviewId}/session`} replace />
}

function App() {
  return (
    <Routes>
      <Route path="/" element={<WelcomePage />} />
      <Route path="/login" element={<RecruiterLoginPage />} />
      <Route path="/signup" element={<RecruiterSignupPage />} />

      {/* Legal and trust pages. Outside both layouts: they belong to the product as a
          whole, not to the recruiter workspace or a candidate's interview. */}
      <Route path="/legal/privacy" element={<PrivacyPage />} />
      <Route path="/legal/terms" element={<TermsPage />} />
      <Route path="/legal/cookies" element={<CookiesPage />} />

      <Route path="/interviews" element={workspace(<InterviewsPage />)} />
      <Route path="/interviews/new" element={workspace(<NewInterviewPage />)} />
      <Route path="/interviews/:jobId" element={workspace(<InterviewDetailPage />)} />
      <Route path="/candidates" element={workspace(<CandidatesPage />)} />
      <Route path="/reports/:interviewId" element={workspace(<ReportPage />)} />

      {/* Candidate-facing. The landing path is what generated invitation links point at and
          must never change shape - see lib/candidateLink. */}
      <Route path="/candidate/interviews/:interviewId" element={candidate(<CandidateLandingPage />)} />
      {/* The live interview brings its own shell. It is a full-bleed dark room with its own
          header, so wrapping it in the light candidate layout would put a white band above it
          and cap it at that layout's reading width. */}
      <Route path="/candidate/interviews/:interviewId/session" element={<InterviewStagePage />} />
      <Route
        path="/candidate/interviews/:interviewId/question/:questionId"
        element={<LegacyQuestionRedirect />}
      />
      {/* Same reasoning as the session route: the interview closes in its own room rather
          than handing the candidate back to a white page the instant they finish. */}
      <Route
        path="/candidate/interviews/:interviewId/complete"
        element={<CandidateCompletePage />}
      />

      {/* Previous recruiter IA, kept as redirects so bookmarks survive the restructure. */}
      <Route path="/recruiter/dashboard" element={<Navigate to="/interviews" replace />} />
      <Route path="/recruiter/interviews/new" element={<Navigate to="/interviews/new" replace />} />

      {/* Unknown URLs go to the public landing page. They used to go to the workspace, which
          meant a mistyped link showed a stranger an authentication screen as if it were the
          product's front door. */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default App
