import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "./components/Layout";
import { FactsPage, PalettePage, RulesPage, SettingsPage, VoicePage } from "./pages/Admin";
import DraftPage from "./pages/DraftPage";
import { DraftsPage, QueuePage } from "./pages/Drafts";
import Landing from "./pages/Landing";
import NewDraft from "./pages/NewDraft";
import "./styles/index.css";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/drafts" element={<AppLayout><DraftsPage /></AppLayout>} />
          <Route path="/drafts/new" element={<AppLayout roles={["creator", "admin"]}><NewDraft /></AppLayout>} />
          <Route path="/drafts/:id" element={<AppLayout><DraftPage /></AppLayout>} />
          <Route path="/queue" element={<AppLayout roles={["reviewer", "admin"]}><QueuePage /></AppLayout>} />
          <Route path="/admin/rules" element={<AppLayout><RulesPage /></AppLayout>} />
          <Route path="/admin/facts" element={<AppLayout><FactsPage /></AppLayout>} />
          <Route path="/admin/voice" element={<AppLayout><VoicePage /></AppLayout>} />
          <Route path="/admin/palette" element={<AppLayout><PalettePage /></AppLayout>} />
          <Route path="/settings" element={<AppLayout><SettingsPage /></AppLayout>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
