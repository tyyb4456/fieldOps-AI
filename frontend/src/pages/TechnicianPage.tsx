import { useAppAuth } from '../auth/app-auth-context'

export function TechnicianPage() {
  const { user } = useAppAuth()

  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6">
      <p className="text-sm font-medium text-sky-400">Technician workspace</p>
      <h1 className="mt-2 text-2xl font-semibold text-white">
        Assigned work orders will appear here.
      </h1>
      <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-300">
        Work-order details, diagnostic checklists, and completion evidence are
        the next implementation step. This page is protected for the technician
        role and confirms that your account has a technician profile
        {user?.technician_id
          ? ` (${user.technician_id.slice(0, 8)}…)`
          : ''}.
      </p>
    </section>
  )
}
