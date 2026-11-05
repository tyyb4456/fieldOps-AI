import { UserButton } from '@clerk/react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { useAppAuth } from '../auth/app-auth-context'
import type { UserRole } from '../lib/api'

const ROLE_LABELS: Record<UserRole, string> = {
  customer: 'Customer',
  technician: 'Technician',
  admin: 'Administrator',
}

const ROLE_HOME: Record<UserRole, string> = {
  customer: '/customer',
  technician: '/technician',
  admin: '/admin',
}

function navLinkClass({ isActive }: { isActive: boolean }): string {
  return [
    'rounded-lg px-3 py-2 text-sm font-medium transition',
    isActive
      ? 'bg-sky-500/15 text-sky-300'
      : 'text-slate-300 hover:bg-slate-800 hover:text-white',
  ].join(' ')
}

export function AppShell() {
  const { user } = useAppAuth()

  return (
    <div className="flex min-h-screen flex-col bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 bg-slate-900/70 backdrop-blur">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <Link to="/" className="flex items-center gap-3">
            <span className="flex size-9 items-center justify-center rounded-xl bg-sky-500 font-bold text-slate-950">
              F
            </span>
            <span className="text-sm font-semibold tracking-wide text-white sm:text-base">
              FieldOps AI
            </span>
          </Link>

          <nav className="hidden items-center gap-1 md:flex">
            {user ? (
              <>
                <NavLink to="/dashboard" className={navLinkClass}>
                  Dashboard
                </NavLink>
                <NavLink
                  to={ROLE_HOME[user.role]}
                  className={navLinkClass}
                >
                  {ROLE_LABELS[user.role]}
                </NavLink>
              </>
            ) : null}
          </nav>

          <div className="flex items-center gap-3">
            {user ? (
              <>
                <span className="hidden text-right text-xs text-slate-400 sm:block">
                  <span className="block font-medium text-slate-200">
                    {user.full_name}
                  </span>
                  {ROLE_LABELS[user.role]}
                </span>
                <UserButton />
              </>
            ) : (
              <Link
                to="/sign-in"
                className="rounded-lg bg-sky-500 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-sky-400"
              >
                Sign in
              </Link>
            )}
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6">
        <Outlet />
      </main>

      <footer className="border-t border-slate-800 px-4 py-4 text-center text-xs text-slate-500">
        FieldOps AI · Application authorization is enforced by the FastAPI
        backend.
      </footer>
    </div>
  )
}
