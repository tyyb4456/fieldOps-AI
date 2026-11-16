import { UserButton, useAuth } from '@clerk/react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { useAppAuth } from '../auth/app-auth-context'
import { PendingMessagesProvider } from '../features/conversations/PendingMessagesProvider'
import {
  ADMIN_NAV_ITEMS,
  CUSTOMER_NAV_ITEMS,
  TECHNICIAN_NAV_ITEMS,
  navigationForRole,
  roleLabel,
} from '../navigation/role-navigation'

function navLinkClass({ isActive }: { isActive: boolean }): string {
  return [
    'rounded-lg px-3 py-2 text-sm font-medium transition',
    isActive
      ? 'bg-sky-500/15 text-sky-300'
      : 'text-slate-300 hover:bg-slate-800 hover:text-white',
  ].join(' ')
}

function Brand() {
  return (
    <Link to="/" className="flex items-center gap-3">
      <span className="flex size-9 items-center justify-center rounded-xl bg-sky-500 font-bold text-slate-950">
        F
      </span>
      <span className="text-sm font-semibold tracking-wide text-white sm:text-base">
        FieldOps AI
      </span>
    </Link>
  )
}

function Navigation({ mobile = false }: { mobile?: boolean }) {
  const { user } = useAppAuth()
  const items = navigationForRole(user?.role)

  if (items.length === 0) {
    return null
  }

  return (
    <nav
      aria-label={mobile ? 'Mobile navigation' : 'Primary navigation'}
      className={
        mobile
          ? 'flex flex-wrap gap-1 border-t border-slate-800 px-4 py-2 md:hidden'
          : 'hidden items-center gap-1 md:flex'
      }
    >
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={navLinkClass}
        >
          {item.label}
        </NavLink>
      ))}
    </nav>
  )
}

function CustomerNavigation() {
  const { user } = useAppAuth()

  if (user?.role !== 'customer') {
    return null
  }

  return (
    <div className="border-t border-slate-800 bg-slate-950/40">
      <nav
        aria-label="Customer navigation"
        className="mx-auto flex w-full max-w-6xl gap-1 overflow-x-auto px-4 py-2 sm:px-6"
      >
        {CUSTOMER_NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={navLinkClass}
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
    </div>
  )
}

function TechnicianNavigation() {
  const { user } = useAppAuth()

  if (user?.role !== 'technician') {
    return null
  }

  return (
    <div className="border-t border-slate-800 bg-slate-950/40">
      <nav
        aria-label="Technician navigation"
        className="mx-auto flex w-full max-w-6xl gap-1 overflow-x-auto px-4 py-2 sm:px-6"
      >
        {TECHNICIAN_NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={navLinkClass}
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
    </div>
  )
}

function AdminNavigation() {
  const { user } = useAppAuth()

  if (user?.role !== 'admin') {
    return null
  }

  return (
    <div className="border-t border-slate-800 bg-slate-950/40">
      <nav
        aria-label="Administrator navigation"
        className="mx-auto flex w-full max-w-6xl gap-1 overflow-x-auto px-4 py-2 sm:px-6"
      >
        {ADMIN_NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={navLinkClass}
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
    </div>
  )
}

export function AppShell() {
  const { user, isLoading } = useAppAuth()
  const { isLoaded, isSignedIn } = useAuth()
  const isProfileLoading = isLoaded && isSignedIn && isLoading

  return (
    <div className="flex min-h-screen flex-col bg-slate-950 text-slate-100">
      <header
        className="border-b border-slate-800 bg-slate-900/70 backdrop-blur"
        aria-busy={!isLoaded || isProfileLoading}
      >
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <Brand />

          <Navigation />

          <div className="flex items-center gap-3">
            {isProfileLoading ? (
              <span
                className="text-xs text-slate-400"
                role="status"
                aria-live="polite"
              >
                Loading account...
              </span>
            ) : user ? (
              <>
                <span className="hidden text-right text-xs text-slate-400 sm:block">
                  <span className="block font-medium text-slate-200">
                    {user.full_name}
                  </span>
                  {roleLabel(user.role)}
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

        <Navigation mobile />
        <CustomerNavigation />
        <TechnicianNavigation />
        <AdminNavigation />
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6">
        <PendingMessagesProvider>
          <Outlet />
        </PendingMessagesProvider>
      </main>

      <footer className="border-t border-slate-800 px-4 py-4 text-center text-xs text-slate-500">
        FieldOps AI. Application authorization is enforced by the FastAPI
        backend.
      </footer>
    </div>
  )
}
