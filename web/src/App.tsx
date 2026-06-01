export default function App() {
  return (
    <div className="flex min-h-screen items-center justify-center px-6">
      <div className="surface w-full max-w-md rounded-(--radius-card) p-10 text-center">
        <p className="font-mono text-xs uppercase tracking-[0.18em] text-(--color-text-faint)">
          Customer Service Agent
        </p>
        <h1 className="mt-6 text-2xl">骨架已就绪</h1>
        <p className="mt-3 text-(--color-text-muted)">
          Linear Dusk · 紫蓝
          <span className="ml-2 inline-block size-2 rounded-full bg-(--color-primary) align-middle" />
        </p>
        <div className="mt-8 flex justify-center gap-2 text-xs text-(--color-text-faint)">
          <span className="rounded-(--radius-control) border border-(--color-border) bg-(--color-surface-2) px-2 py-1 font-mono">
            React 19
          </span>
          <span className="rounded-(--radius-control) border border-(--color-border) bg-(--color-surface-2) px-2 py-1 font-mono">
            Tailwind v4
          </span>
          <span className="rounded-(--radius-control) border border-(--color-border) bg-(--color-surface-2) px-2 py-1 font-mono">
            Framer
          </span>
        </div>
      </div>
    </div>
  )
}
