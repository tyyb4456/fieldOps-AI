import { Link } from 'react-router-dom'

export function UnauthorizedPage() {
  return (
    <div className="mx-auto flex min-h-[50vh] max-w-lg flex-col items-center justify-center gap-4 text-center">
      <div className="rounded-full bg-amber-400/10 p-3 text-amber-300">
        <svg
          className="size-6"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M12 15v2m0 4h.01M5 11V7a7 7 0 0 1 14 0v4M5 11h14v10H5V11Z"
          />
        </svg>
      </div>
      <div>
        <h1 className="text-xl font-semibold text-white">
          You do not have access to this area
        </h1>
        <p className="mt-2 text-sm text-slate-300">
          Your FieldOps role does not include this workspace. If you believe
          this is a mistake, contact an administrator.
        </p>
      </div>
      <Link
        to="/dashboard"
        className="rounded-lg bg-sky-500 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-sky-400"
      >
        Back to dashboard
      </Link>
    </div>
  )
}
