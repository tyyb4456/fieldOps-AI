import { Link } from 'react-router-dom'
import { useAppAuth } from '../auth/app-auth-context'
import type { UserRole } from '../lib/api'

const ROLE_LABELS: Record<UserRole, string> = {
  customer: 'Customer',
  technician: 'Technician',
  admin: 'Administrator',
}

const ROLE_DESTINATIONS: Record<UserRole, string> = {
  customer: '/customer',
  technician: '/technician',
  admin: '/admin',
}

export function DashboardPage() {
  const { user } = useAppAuth()

  if (!user) {
    return null
  }

  return (
    <div className="grid gap-6">
      <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6">
        <p className="text-sm font-medium text-sky-400">Dashboard</p>
        <h1 className="mt-2 text-2xl font-semibold text-white">
          Welcome, {user.full_name}
        </h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300">
          Your application role comes from the FieldOps database, not from
          Clerk metadata. The API enforces the same role and object-level rules
          on every request.
        </p>

        <dl className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-4">
            <dt className="text-xs uppercase tracking-wide text-slate-500">
              Role
            </dt>
            <dd className="mt-1 text-sm font-medium text-slate-100">
              {ROLE_LABELS[user.role]}
            </dd>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-4">
            <dt className="text-xs uppercase tracking-wide text-slate-500">
              Email
            </dt>
            <dd className="mt-1 truncate text-sm font-medium text-slate-100">
              {user.email ?? 'Not provided'}
            </dd>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-4">
            <dt className="text-xs uppercase tracking-wide text-slate-500">
              Account
            </dt>
            <dd className="mt-1 text-sm font-medium text-emerald-300">
              {user.is_active ? 'Active' : 'Inactive'}
            </dd>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-4">
            <dt className="text-xs uppercase tracking-wide text-slate-500">
              Profile
            </dt>
            <dd className="mt-1 truncate text-sm font-medium text-slate-100">
              {user.customer_id
                ? `Customer ${user.customer_id.slice(0, 8)}`
                : user.technician_id
                  ? `Technician ${user.technician_id.slice(0, 8)}`
                  : 'Administrator'}
            </dd>
          </div>
        </dl>

        <Link
          to={ROLE_DESTINATIONS[user.role]}
          className="mt-6 inline-flex rounded-xl bg-sky-500 px-5 py-3 text-sm font-semibold text-slate-950 transition hover:bg-sky-400"
        >
          Open {ROLE_LABELS[user.role]} workspace
        </Link>
      </section>
    </div>
  )
}
