import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { HashRouter, Navigate, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppShell } from './components/layout/app-shell'
import DocumentsPage from './pages/DocumentsPage'
import FaqsPage from './pages/FaqsPage'
import AssistantPage from './pages/AssistantPage'
import EvaluationPage from './pages/EvaluationPage'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 5_000,
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <HashRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/" element={<Navigate to="/documents" replace />} />
            <Route path="/documents" element={<DocumentsPage />} />
            <Route path="/faqs" element={<FaqsPage />} />
            <Route path="/assistant" element={<AssistantPage />} />
            <Route path="/evaluation" element={<EvaluationPage />} />
            <Route path="*" element={<Navigate to="/documents" replace />} />
          </Route>
        </Routes>
      </HashRouter>
    </QueryClientProvider>
  </StrictMode>,
)
