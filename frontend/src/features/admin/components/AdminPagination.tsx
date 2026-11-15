export function AdminPagination({
  offset,
  pageSize,
  total,
  noun,
  onOffsetChange,
}: {
  offset: number
  pageSize: number
  total: number
  noun: string
  onOffsetChange: (offset: number) => void
}) {
  const page = Math.floor(offset / pageSize) + 1
  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <button
        type="button"
        onClick={() => onOffsetChange(Math.max(0, offset - pageSize))}
        disabled={offset === 0}
        className="rounded-lg border border-slate-700 px-4 py-2 text-sm font-medium text-slate-200 transition hover:border-slate-500 disabled:cursor-not-allowed disabled:opacity-40"
      >
        Previous
      </button>
      <span className="text-xs text-slate-500">
        Page {page} of {totalPages} - showing {total === 0 ? 0 : offset + 1}-
        {Math.min(offset + pageSize, total)} of {total} {noun}
      </span>
      <button
        type="button"
        onClick={() => onOffsetChange(offset + pageSize)}
        disabled={offset + pageSize >= total}
        className="rounded-lg border border-slate-700 px-4 py-2 text-sm font-medium text-slate-200 transition hover:border-slate-500 disabled:cursor-not-allowed disabled:opacity-40"
      >
        Next
      </button>
    </div>
  )
}
