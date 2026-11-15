import { useState } from 'react'
import { Link } from 'react-router-dom'
import { EmptyState } from '../../../components/EmptyState'
import { ErrorScreen } from '../../../components/ErrorScreen'
import { LoadingScreen } from '../../../components/LoadingScreen'
import { PageHeader } from '../../../components/PageHeader'
import { useApiClient } from '../../../lib/api/api-client-context'
import { useAsyncData } from '../../../lib/hooks/use-async-data'
import { listAdminTechnicians } from '../api'
import { AdminPagination } from '../components/AdminPagination'
import { AvailabilityBadge } from '../components/AdminBadges'
import { adminTechnicianErrorMessage } from '../errors'
import { ADMIN_ROUTES } from '../routes'

const PAGE_SIZE = 20

function skillEntries(
  skills: Record<string, unknown>,
): Array<[string, string]> {
  return Object.entries(skills).map(([key, value]) => [
    key,
    typeof value === 'string' ? value : JSON.stringify(value),
  ])
}

export function AdminTechniciansPage() {
  const apiClient = useApiClient()
  const [offset, setOffset] = useState(0)

  const { data, error, isLoading, reload } = useAsyncData(
    (signal) =>
      listAdminTechnicians(
        apiClient,
        { limit: PAGE_SIZE, offset },
        signal,
      ),
    [apiClient, offset],
  )

  return (
    <div className="grid gap-6">
      <PageHeader
        eyebrow="Administrator"
        title="Eligible technicians"
        description="Technicians returned by the assignment eligibility endpoint. Availability and workload affect assignment decisions."
      />

      {isLoading ? (
        <LoadingScreen label="Loading technicians..." />
      ) : error || !data ? (
        <ErrorScreen
          message={adminTechnicianErrorMessage(error)}
          onRetry={reload}
        />
      ) : data.items.length === 0 ? (
        <EmptyState
          title="No eligible technicians"
          description="Technician eligibility is managed by the service team and the API."
        />
      ) : (
        <>
          <ul className="grid gap-3">
            {data.items.map((technician) => (
              <li
                key={technician.id}
                className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <AvailabilityBadge isAvailable={technician.is_available} />
                  <span className="text-base font-semibold text-white">
                    {technician.full_name}
                  </span>
                  {technician.service_area ? (
                    <span className="text-xs text-slate-500">
                      {technician.service_area}
                    </span>
                  ) : null}
                </div>
                {technician.email ? (
                  <p className="mt-1 text-sm text-slate-400">
                    {technician.email}
                  </p>
                ) : null}
                {skillEntries(technician.skills).length > 0 ? (
                  <div className="mt-3">
                    <h2 className="text-xs uppercase tracking-wide text-slate-500">
                      Skills
                    </h2>
                    <ul className="mt-1 flex flex-wrap gap-2">
                      {skillEntries(technician.skills).map(([key, value]) => (
                        <li
                          key={key}
                          className="rounded-full border border-slate-700 bg-slate-800/70 px-2.5 py-0.5 text-xs text-slate-300"
                        >
                          {key}: {value}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                <p className="mt-3 font-mono text-xs text-slate-500">
                  Technician {technician.id}
                </p>
              </li>
            ))}
          </ul>
          <AdminPagination
            offset={offset}
            pageSize={PAGE_SIZE}
            total={data.total}
            noun="technicians"
            onOffsetChange={setOffset}
          />
        </>
      )}

      <Link
        to={ADMIN_ROUTES.assignments}
        className="w-fit rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-medium text-slate-200 transition hover:border-slate-500"
      >
        Coordinate assignments
      </Link>
    </div>
  )
}
