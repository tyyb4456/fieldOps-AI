export function AdminPage() {
  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6">
      <p className="text-sm font-medium text-sky-400">Administrator workspace</p>
      <h1 className="mt-2 text-2xl font-semibold text-white">
        Operational oversight will live here.
      </h1>
      <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-300">
        Complaint triage, technician management, and work-order assignment are
        the next implementation step. This page is protected for the
        administrator role. Administrators do not receive a customer or
        technician operational profile.
      </p>
    </section>
  )
}
