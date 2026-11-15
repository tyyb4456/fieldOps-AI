import type { ReactNode } from 'react'

export function FormError({ message }: { message: string | null }) {
  if (!message) {
    return null
  }

  return (
    <div
      role="alert"
      className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200"
    >
      {message}
    </div>
  )
}

export function Notice({ children }: { children: ReactNode }) {
  return (
    <div
      role="status"
      className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200"
    >
      {children}
    </div>
  )
}

export function InlineWarning({ children }: { children: ReactNode }) {
  return (
    <div
      role="status"
      className="rounded-xl border border-amber-400/30 bg-amber-400/10 px-4 py-3 text-sm text-amber-200"
    >
      {children}
    </div>
  )
}
