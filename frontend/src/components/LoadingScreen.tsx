export function LoadingScreen({
  label = 'Loading…',
}: {
  label?: string
}) {
  return (
    <div className="flex min-h-[50vh] items-center justify-center">
      <div className="flex items-center gap-3 text-sm text-slate-300">
        <span
          className="size-5 animate-spin rounded-full border-2 border-slate-600 border-t-sky-400"
          aria-hidden="true"
        />
        <span>{label}</span>
      </div>
    </div>
  )
}
