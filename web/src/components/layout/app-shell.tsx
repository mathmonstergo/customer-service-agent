import { Outlet } from 'react-router-dom'
import { lazy, Suspense, useEffect, useState } from 'react'
import { TooltipProvider } from '@/components/ui/tooltip'
import { Toaster } from '@/components/ui/toaster'
import { Sidebar } from './sidebar'
import { Topbar } from './topbar'

const CommandPalette = lazy(() => import('@/components/shared/command-palette'))

// 应用外壳只加载常驻导航；命令面板按首次触发懒加载，避免首屏 bundle 过大。
export function AppShell() {
  const [commandOpen, setCommandOpen] = useState(false)
  const [commandLoaded, setCommandLoaded] = useState(false)

  useEffect(() => {
    // 全局快捷键保持轻量常驻；真正的命令面板代码在首次打开时再下载。
    const onCommandShortcut = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setCommandLoaded(true)
        setCommandOpen((open) => !open)
      }
    }

    window.addEventListener('keydown', onCommandShortcut)
    return () => window.removeEventListener('keydown', onCommandShortcut)
  }, [])

  return (
    <TooltipProvider delayDuration={200}>
      <div className="flex h-screen bg-(--color-bg)">
        <Sidebar />
        <main className="flex min-w-0 flex-1 flex-col">
          <Topbar />
          <div className="min-h-0 flex-1 overflow-hidden">
            <Outlet />
          </div>
        </main>
        <Toaster />
        {commandLoaded && (
          <Suspense fallback={null}>
            <CommandPalette open={commandOpen} onOpenChange={setCommandOpen} />
          </Suspense>
        )}
      </div>
    </TooltipProvider>
  )
}
