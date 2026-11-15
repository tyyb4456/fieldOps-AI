import type { ReactNode } from 'react'

export type BadgeTone =
  | 'neutral'
  | 'info'
  | 'success'
  | 'warning'
  | 'danger'

const TONE_CLASSES: Record<BadgeTone, string> = {
  neutral: 'border-slate-700 bg-slate-800/70 text-slate-300',
  info: 'border-sky-500/30 bg-sky-500/10 text-sky-300',
  success: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
  warning: 'border-amber-400/30 bg-amber-400/10 text-amber-300',
  danger: 'border-rose-500/30 bg-rose-500/10 text-rose-300',
}

export function Badge({
  tone = 'neutral',
  children,
}: {
  tone?: BadgeTone
  children: ReactNode
}) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${TONE_CLASSES[tone]}`}
    >
      {children}
    </span>
  )
}
