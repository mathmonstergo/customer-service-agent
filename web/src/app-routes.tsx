import { lazy, Suspense } from 'react'
import { HashRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/layout/app-shell'

const DocumentsPage = lazy(() => import('./pages/DocumentsPage'))
const FaqsPage = lazy(() => import('./pages/FaqsPage'))
const AssistantPage = lazy(() => import('./pages/AssistantPage'))
const EvaluationPage = lazy(() => import('./pages/EvaluationPage'))
const KnowledgeGraphPage = lazy(() => import('./pages/KnowledgeGraphPage'))
const SettingsPage = lazy(() => import('./pages/SettingsPage'))

const pageFallback = (
  <div className="flex h-full items-center justify-center text-sm text-(--color-text-muted)">
    加载中...
  </div>
)

// 主路由只保留布局和当前页面 chunk；各业务页按路由懒加载，降低首屏 JS 体积。
export function AppRoutes() {
  return (
    <HashRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<Navigate to="/documents" replace />} />
          <Route
            path="/documents"
            element={
              <Suspense fallback={pageFallback}>
                <DocumentsPage />
              </Suspense>
            }
          />
          <Route
            path="/faqs"
            element={
              <Suspense fallback={pageFallback}>
                <FaqsPage />
              </Suspense>
            }
          />
          <Route
            path="/assistant"
            element={
              <Suspense fallback={pageFallback}>
                <AssistantPage />
              </Suspense>
            }
          />
          <Route
            path="/knowledge-graph"
            element={
              <Suspense fallback={pageFallback}>
                <KnowledgeGraphPage />
              </Suspense>
            }
          />
          <Route
            path="/evaluation"
            element={
              <Suspense fallback={pageFallback}>
                <EvaluationPage />
              </Suspense>
            }
          />
          <Route
            path="/settings"
            element={
              <Suspense fallback={pageFallback}>
                <SettingsPage />
              </Suspense>
            }
          />
          <Route path="*" element={<Navigate to="/documents" replace />} />
        </Route>
      </Routes>
    </HashRouter>
  )
}
