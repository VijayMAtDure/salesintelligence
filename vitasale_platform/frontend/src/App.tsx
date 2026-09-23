import { Navigate, Route, BrowserRouter, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider, useAuth } from "./api/AuthContext";
import { Layout } from "./components/Layout";
import { IngestionPage } from "./pages/IngestionPage";
import { PipelinePage } from "./pages/PipelinePage";
import { TrainingPage } from "./pages/TrainingPage";
import { ModelsPage } from "./pages/ModelsPage";
import { InferencePage } from "./pages/InferencePage";
import { ActivityPage } from "./pages/ActivityPage";
import { SandboxPage } from "./pages/SandboxPage";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { SystemMapPage } from "./pages/SystemMapPage";
import { AssistantPage } from "./pages/AssistantPage";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1 } },
});

/**
 * No visible login screen for now (see AuthContext.tsx) — auto-login runs on load. If it
 * genuinely fails (backend down, dev credentials wrong), show that directly rather than
 * silently redirecting to an unrouted login page the user was told doesn't exist right now.
 * LoginPage.tsx itself is untouched and can be wired back in by re-adding its route here.
 */
function AppGate({ children }: { children: React.ReactNode }) {
  const { ready, authenticated } = useAuth();
  if (!ready) return null;
  if (!authenticated) {
    return (
      <div style={{ padding: 40, fontFamily: "system-ui, sans-serif" }}>
        <h2>Couldn't connect</h2>
        <p style={{ color: "#64748b" }}>
          Auto-login failed — the API may be unreachable, or the dev credentials in
          frontend/.env are out of date.
        </p>
      </div>
    );
  }
  return <>{children}</>;
}

function AppRoutes() {
  return (
    <AppGate>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/ingestion" element={<IngestionPage />} />
          <Route path="/pipeline" element={<PipelinePage />} />
          <Route path="/training" element={<TrainingPage />} />
          <Route path="/models" element={<ModelsPage />} />
          <Route path="/predict" element={<InferencePage />} />
          <Route path="/activity" element={<ActivityPage />} />
          <Route path="/sandbox" element={<SandboxPage />} />
          <Route path="/analytics" element={<AnalyticsPage />} />
          <Route path="/map" element={<SystemMapPage />} />
          <Route path="/assistant" element={<AssistantPage />} />
          <Route path="/" element={<Navigate to="/ingestion" replace />} />
          <Route path="*" element={<Navigate to="/ingestion" replace />} />
        </Route>
      </Routes>
    </AppGate>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <AppRoutes />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
