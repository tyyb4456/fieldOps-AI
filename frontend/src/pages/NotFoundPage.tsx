import { Link } from 'react-router-dom'

export function NotFoundPage() {
  return (
    <div className="mx-auto flex min-h-[50vh] max-w-lg flex-col items-center justify-center gap-4 text-center">
      <p className="text-5xl font-semibold text-slate-700">404</p>
      <h1 className="text-xl font-semibold text-white">Page not found</h1>
      <p className="text-sm text-slate-300">
        The page you requested does not exist.
      </p>
      <Link
        to="/"
        className="rounded-lg bg-sky-500 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-sky-400"
      >
        Return home
      </Link>
    </div>
  )
}
