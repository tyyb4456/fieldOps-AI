import { Link } from 'react-router-dom'
import { EmptyState } from '../../../components/EmptyState'
import { PageHeader } from '../../../components/PageHeader'
import { ErrorScreen } from '../../../components/ErrorScreen'
import { LoadingScreen } from '../../../components/LoadingScreen'
import { apiErrorMessage } from '../../../lib/api/errors'
import { formatDate, formatDateTime } from '../../../lib/format'
import { useAsyncData } from '../../../lib/hooks/use-async-data'
import { useApiClient } from '../../../lib/api/api-client-context'
import { ComplaintStatusBadge } from '../../complaints/components/ComplaintBadges'
import { complaintStatusLabel } from '../../complaints/labels'
import {
  loadCustomerDashboard,
  summarizeCustomerDashboard,
} from '../dashboard'
import {
  CUSTOMER_ROUTES,
  customerComplaintPath,
  customerEquipmentPath,
} from '../routes'

function SummaryCard({
  label,
  value,
  note,
}: {
  label: string
  value: number
  note?: string
}) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
        {label}
      </p>
      <p className="mt-2 text-3xl font-semibold text-white">{value}</p>
      {note ? <p className="mt-1 text-xs text-slate-500">{note}</p> : null}
    </div>
  )
}

export function CustomerDashboardPage() {
  const apiClient = useApiClient()
  const { data, error, isLoading, reload } = useAsyncData(
    (signal) => loadCustomerDashboard(apiClient, signal),
    [apiClient],
  )

  if (isLoading) {
    return <LoadingScreen label="Loading your dashboard..." />
  }

  if (error || !data) {
    return (
      <ErrorScreen
        message={apiErrorMessage(
          error,
          'Unable to load your customer dashboard.',
        )}
        onRetry={reload}
      />
    )
  }

  const { profile, equipment, complaints } = data
  const summary = summarizeCustomerDashboard(equipment, complaints)
  const recentComplaints = complaints.items.slice(0, 5)
  const recentEquipment = equipment.items.slice(0, 3)

  return (
    <div className="grid gap-6">
      <PageHeader
        eyebrow="Customer dashboard"
        title={`Welcome, ${profile.full_name}`}
        description="Review your registered equipment, follow your complaints, and submit a new service request."
        actions={
          <>
            <Link
              to={CUSTOMER_ROUTES.newComplaint}
              className="rounded-xl bg-sky-500 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-sky-400"
            >
              Report a problem
            </Link>
            <Link
              to={CUSTOMER_ROUTES.profile}
              className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-semibold text-slate-200 transition hover:border-slate-500 hover:text-white"
            >
              View profile
            </Link>
          </>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <SummaryCard
          label="Registered equipment"
          value={summary.equipmentTotal}
          note={summary.equipmentNote ?? undefined}
        />
        <SummaryCard
          label="Complaints submitted"
          value={summary.complaintTotal}
          note={summary.complaintNote ?? undefined}
        />
        <SummaryCard
          label="Awaiting your response"
          value={summary.awaitingResponse}
          note={summary.awaitingResponseNote ?? undefined}
        />
      </div>

      <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-base font-semibold text-white">My equipment</h2>
          <Link
            to={CUSTOMER_ROUTES.equipment}
            className="text-sm font-medium text-sky-300 hover:text-sky-200"
          >
            View all equipment
          </Link>
        </div>

        {recentEquipment.length === 0 ? (
          <div className="mt-4">
            <EmptyState
              title="No equipment registered"
              description="Register your inverter, battery, or other equipment to attach it to future complaints."
              action={
                <Link
                  to={CUSTOMER_ROUTES.newEquipment}
                  className="inline-flex rounded-lg bg-sky-500 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-sky-400"
                >
                  Register equipment
                </Link>
              }
            />
          </div>
        ) : (
          <ul className="mt-4 grid gap-3">
            {recentEquipment.map((item) => (
              <li key={item.id}>
                <Link
                  to={customerEquipmentPath(item.id)}
                  className="flex flex-col gap-1 rounded-xl border border-slate-800 bg-slate-950/40 p-4 transition hover:border-sky-500/40 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div>
                    <p className="text-sm font-medium text-white">
                      {item.manufacturer} {item.model}
                    </p>
                    <p className="text-xs text-slate-400">
                      {item.equipment_type}
                      {item.serial_number
                        ? ` - Serial ${item.serial_number}`
                        : ''}
                    </p>
                  </div>
                  <p className="text-xs text-slate-500">
                    Registered {formatDate(item.created_at)}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <div className="grid gap-6 lg:grid-cols-[1.4fr_0.6fr]">
        <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-base font-semibold text-white">
              Recent complaints
            </h2>
            <Link
              to={CUSTOMER_ROUTES.complaints}
              className="text-sm font-medium text-sky-300 hover:text-sky-200"
            >
              View all complaints
            </Link>
          </div>

          {recentComplaints.length === 0 ? (
            <div className="mt-4">
              <EmptyState
                title="No complaints yet"
                description="When you report a problem, it will appear here with its current status."
                action={
                  <Link
                    to={CUSTOMER_ROUTES.newComplaint}
                    className="inline-flex rounded-lg bg-sky-500 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-sky-400"
                  >
                    Submit a complaint
                  </Link>
                }
              />
            </div>
          ) : (
            <ul className="mt-4 grid gap-3">
              {recentComplaints.map((complaint) => (
                <li key={complaint.id}>
                  <Link
                    to={customerComplaintPath(complaint.id)}
                    className="block rounded-xl border border-slate-800 bg-slate-950/40 p-4 transition hover:border-sky-500/40"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <ComplaintStatusBadge status={complaint.status} />
                      <span className="text-xs text-slate-500">
                        {formatDateTime(complaint.created_at)}
                      </span>
                    </div>
                    <p className="mt-2 line-clamp-2 text-sm leading-6 text-slate-200">
                      {complaint.description}
                    </p>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
          <h2 className="text-base font-semibold text-white">
            Complaint status
          </h2>
          {summary.visibleStatuses.length === 0 ? (
            <p className="mt-4 text-sm text-slate-400">
              No complaint activity to summarize yet.
            </p>
          ) : (
            <>
              <ul className="mt-4 grid gap-2">
                {summary.visibleStatuses.map((status) => (
                  <li
                    key={status}
                    className="flex items-center justify-between gap-3 rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2"
                  >
                    <span className="text-xs text-slate-300">
                      {complaintStatusLabel(status)}
                    </span>
                    <span className="text-sm font-semibold text-white">
                      {summary.statusCounts[status] ?? 0}
                    </span>
                  </li>
                ))}
              </ul>
              {summary.statusBreakdownNote ? (
                <p className="mt-3 text-xs leading-5 text-slate-500">
                  {summary.statusBreakdownNote}
                </p>
              ) : null}
            </>
          )}
        </section>
      </div>
    </div>
  )
}
