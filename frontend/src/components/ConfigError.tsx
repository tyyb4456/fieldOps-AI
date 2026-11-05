export function ConfigError() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 px-6 text-slate-100">
      <div className="max-w-xl rounded-2xl border border-amber-400/30 bg-amber-400/5 p-6">
        <h1 className="text-lg font-semibold text-amber-200">
          Clerk is not configured
        </h1>
        <p className="mt-2 text-sm text-slate-300">
          Set <code className="text-amber-200">VITE_CLERK_PUBLISHABLE_KEY</code>{' '}
          in <code className="text-amber-200">frontend/.env.local</code> and
          restart the Vite development server.
        </p>
        <p className="mt-3 text-sm text-slate-400">
          Only the publishable key belongs in the frontend. Never add the Clerk
          secret key to a Vite environment variable.
        </p>
      </div>
    </div>
  )
}
