import { Toaster as Sonner } from 'sonner'

export function Toaster() {
  return (
    <Sonner
      position="top-center"
      offset={24}
      gap={8}
      visibleToasts={5}
      theme="dark"
      toastOptions={{
        duration: 2400,
        unstyled: false,
        classNames: {
          toast:
            'group flex items-center gap-3 rounded-(--radius-control) border bg-(--color-surface) text-(--color-text) px-3 py-2.5 text-[13px] shadow-(--shadow-elevated)',
          title: 'text-(--color-text) font-[500]',
          description: 'text-(--color-text-muted) text-[12px]',
          actionButton: 'rounded-(--radius-control) bg-(--color-primary) text-white px-2 py-1',
          cancelButton: 'rounded-(--radius-control) bg-(--color-surface-2) text-(--color-text-muted) px-2 py-1',
          closeButton:
            'border border-(--color-border) bg-(--color-surface-2) text-(--color-text-muted) hover:text-(--color-text)',
          error: 'border-(--color-danger)/30',
          success: 'border-(--color-success)/30',
          warning: 'border-(--color-warning)/30',
          info: 'border-(--color-border)',
        },
      }}
      style={
        {
          ['--normal-bg']: 'var(--color-surface)',
          ['--normal-text']: 'var(--color-text)',
          ['--normal-border']: 'var(--color-border)',
          ['--success-bg']: 'var(--color-surface)',
          ['--success-text']: 'var(--color-success)',
          ['--success-border']: 'color-mix(in srgb, var(--color-success) 30%, transparent)',
          ['--error-bg']: 'var(--color-surface)',
          ['--error-text']: 'var(--color-danger)',
          ['--error-border']: 'color-mix(in srgb, var(--color-danger) 30%, transparent)',
        } as React.CSSProperties
      }
    />
  )
}
