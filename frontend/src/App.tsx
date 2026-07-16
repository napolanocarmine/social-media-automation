import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "./components/AppLayout";
import { AiOutputPage } from "./pages/AiOutputPage";
import { ApprovePage } from "./pages/ApprovePage";
import { AutomationPage } from "./pages/AutomationPage";
import { HomePage } from "./pages/HomePage";
import { PlanPage } from "./pages/PlanPage";
import { PublishPage } from "./pages/PublishPage";
import { SelectDrivePage } from "./pages/SelectDrivePage";

const queryClient = new QueryClient();

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<AppLayout />}>
            <Route index element={<HomePage />} />
            <Route path="workflow/select" element={<SelectDrivePage />} />
            <Route path="workflow/output" element={<AiOutputPage />} />
            <Route path="workflow/approve" element={<ApprovePage />} />
            <Route path="workflow/plan" element={<PlanPage />} />
            <Route path="workflow/publish" element={<PublishPage />} />
            <Route path="automation" element={<AutomationPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
