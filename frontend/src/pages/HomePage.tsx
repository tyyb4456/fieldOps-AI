import { Link } from 'react-router-dom'
import { useAuth } from '@clerk/react'
import { useAppAuth } from '../auth/app-auth-context'

const ROLE_HOME = {
  customer: '/customer',
  technician: '/technician',
  admin: '/admin',
} as const

export function HomePage() {
  const { isLoaded, isSignedIn } = useAuth()
  const { user } = useAppAuth()

  return (
    <div className="grid gap-10 py-10 lg:grid-cols-[1.2fr_0.8fr] lg:items-center">
      <section>
        <p className="text-sm font-semibold uppercase tracking-[0.2em] text-sky-400">
          Field-service coordination
        </p>
        <h1 className="mt-4 max-w-2xl text-4xl font-semibold tracking-tight text-white sm:text-5xl">
          One secure workspace for every field-service role.
        </h1>
        <p className="mt-5 max-w-2xl text-base leading-7 text-slate-300">
          Customers report problems, technicians complete work, and
          administrators coordinate operations. Identity is handled by Clerk;
          every business permission is enforced by the FieldOps API and its
          database.
        </p>

        <div className="mt-8 flex flex-wrap items-center gap-3">
          {isLoaded && isSignedIn ? (
            <Link
              to={user ? ROLE_HOME[user.role] : '/dashboard'}
              className="rounded-xl bg-sky-500 px-5 py-3 text-sm font-semibold text-slate-950 transition hover:bg-sky-400"
            >
              Open your workspace
            </Link>
          ) : (
            <>
              <Link
                to="/sign-in"
                className="rounded-xl bg-sky-500 px-5 py-3 text-sm font-semibold text-slate-950 transition hover:bg-sky-400"
              >
                Sign in
              </Link>
              <Link
                to="/sign-up"
                className="rounded-xl border border-slate-700 px-5 py-3 text-sm font-semibold text-slate-200 transition hover:border-slate-500 hover:text-white"
              >
                Create an account
              </Link>
            </>
          )}
        </div>
      </section>

      <section className="grid gap-4">
        {[
          {
            title: 'Customers',
            body: 'Create an account, describe the problem, and follow the repair from report to completion.',
          },
          {
            title: 'Technicians',
            body: 'Open assigned work orders, review diagnostic guidance, and record what was actually done.',
          },
          {
            title: 'Administrators',
            body: 'Coordinate complaints, technicians, and work orders with role-aware oversight.',
          },
        ].map((card) => (
          <article
            key={card.title}
            className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5"
          >
            <h2 className="text-sm font-semibold text-white">
              {card.title}
            </h2>
            <p className="mt-2 text-sm leading-6 text-slate-300">
              {card.body}
            </p>
          </article>
        ))}
      </section>
    </div>
  )
}
