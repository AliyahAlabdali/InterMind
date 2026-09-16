import { Navigate, Route, Routes } from "react-router-dom"
import { RecruiterLayout } from "./layouts/RecruiterLayout"
import { CandidateLayout } from "./layouts/CandidateLayout"
import { DashboardPage } from "./pages/recruiter/DashboardPage"
import { NewInterviewPage } from "./pages/recruiter/NewInterviewPage"
import { JobAnalysisPage } from "./pages/recruiter/JobAnalysisPage"
import { InterviewPlanPage } from "./pages/recruiter/InterviewPlanPage"
import { InterviewCandidatesPage } from "./pages/recruiter/InterviewCandidatesPage"
import { ReportPage } from "./pages/recruiter/ReportPage"
import { CandidateLandingPage } from "./pages/candidate/CandidateLandingPage"
import { CandidateQuestionPage } from "./pages/candidate/CandidateQuestionPage"
import { CandidateCompletePage } from "./pages/candidate/CandidateCompletePage"

function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/recruiter/dashboard" replace />} />

      <Route
        path="/recruiter/dashboard"
        element={
          <RecruiterLayout>
            <DashboardPage />
          </RecruiterLayout>
        }
      />
      <Route
        path="/recruiter/interviews/new"
        element={
          <RecruiterLayout>
            <NewInterviewPage />
          </RecruiterLayout>
        }
      />
      {/* The interview/role's command center: candidates, statuses, reports - the recruiter's
          primary destination for an existing interview (see the recruiter-workflow review). */}
      <Route
        path="/recruiter/interviews/:jobId"
        element={
          <RecruiterLayout>
            <InterviewCandidatesPage />
          </RecruiterLayout>
        }
      />
      <Route
        path="/recruiter/interviews/:jobId/job-analysis"
        element={
          <RecruiterLayout>
            <JobAnalysisPage />
          </RecruiterLayout>
        }
      />
      <Route
        path="/recruiter/interviews/:jobId/plan"
        element={
          <RecruiterLayout>
            <InterviewPlanPage />
          </RecruiterLayout>
        }
      />
      <Route
        path="/recruiter/interviews/:jobId/reports/:interviewId"
        element={
          <RecruiterLayout>
            <ReportPage />
          </RecruiterLayout>
        }
      />

      <Route
        path="/candidate/interviews/:interviewId"
        element={
          <CandidateLayout>
            <CandidateLandingPage />
          </CandidateLayout>
        }
      />
      <Route
        path="/candidate/interviews/:interviewId/question/:questionId"
        element={
          <CandidateLayout>
            <CandidateQuestionPage />
          </CandidateLayout>
        }
      />
      <Route
        path="/candidate/interviews/:interviewId/complete"
        element={
          <CandidateLayout>
            <CandidateCompletePage />
          </CandidateLayout>
        }
      />

      <Route path="*" element={<Navigate to="/recruiter/dashboard" replace />} />
    </Routes>
  )
}

export default App
