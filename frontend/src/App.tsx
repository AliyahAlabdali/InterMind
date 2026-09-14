import { Route, Routes } from "react-router-dom"
import { MainLayout } from "./layouts/MainLayout"
import { HomePage } from "./pages/HomePage"
import { InterviewPlanPage } from "./pages/InterviewPlanPage"
import { CandidateInterviewPage } from "./pages/CandidateInterviewPage"
import { InterviewReportPage } from "./pages/InterviewReportPage"

function App() {
  return (
    <MainLayout>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/jobs/:jobId/plan" element={<InterviewPlanPage />} />
        <Route path="/interviews/:interviewId" element={<CandidateInterviewPage />} />
        <Route path="/interviews/:interviewId/report" element={<InterviewReportPage />} />
      </Routes>
    </MainLayout>
  )
}

export default App
