import type { ReactNode } from 'react'

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string
  description: string
  action?: ReactNode
}) {
  return (
    <div className="rounded-2xl border border-dashed border-slate-700 bg-slate-900/40 p-8 text-center">
      <h2 className="text-base font-semibold text-white">{title}</h2>
      <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-slate-400">
        {description}
      </p>
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  )
}
