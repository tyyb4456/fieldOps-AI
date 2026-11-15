import { useState } from 'react'
import { Link } from 'react-router-dom'
import { EmptyState } from '../../../components/EmptyState'
import { ErrorScreen } from '../../../components/ErrorScreen'
import { Notice } from '../../../components/Feedback'
import { LoadingScreen } from '../../../components/LoadingScreen'
import { PageHeader } from '../../../components/PageHeader'
import { useApiClient } from '../../../lib/api/api-client-context'
import { apiErrorMessage } from '../../../lib/api/errors'
import { formatDateTime } from '../../../lib/format'
import { useAsyncData } from '../../../lib/hooks/use-async-data'
import { PriorityBadge } from '../../complaints/components/ComplaintBadges'
import { AssignmentActions } from '../components/AssignmentActions'
import {
  AssignmentStatusBadge,
  WorkOrderStatusBadge,
} from '../components/TechnicianBadges'
import {
  loadTechnicianDashboard,
  selectDashboardPreviews,
  summarizeTechnicianDashboard,
} from '../dashboard'
import { TECHNICIAN_ROUTES, technicianWorkOrderPath } from '../routes'

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
      {note ? <p className="mt-1 text-xs leading-5 text-slate-500">{note}</p> : null}
    </div>
  )
}

export function TechnicianDashboardPage() {
  const apiClient = useApiClient()
  const { data, error, isLoading, reload } = useAsyncData(
    (signal) => loadTechnicianDashboard(apiClient, signal),
    [apiClient],
  )
  const [notice, setNotice] = useState<string | null>(null)

  if (isLoading) {
    return <LoadingScreen label="Loading your technician dashboard..." />
  }

  if (error || !data) {
    return (
      <ErrorScreen
        message={apiErrorMessage(
          error,
          'Unable to load your technician dashboard.',
        )}
        onRetry={reload}
      />
    )
  }

  const summary = summarizeTechnicianDashboard(
    data.workOrders,
    data.offeredAssignments,
  )
  const previews = selectDashboardPreviews(
    data.workOrders,
    data.offeredAssignments,
  )

  return (
    <div className="grid gap-6">
      <PageHeader
        eyebrow="Technician dashboard"
        title="Your field work at a glance"
        description="Review offered assignments, continue active work orders, and keep service records up to date."
        actions={
          <>
            <Link
              to={TECHNICIAN_ROUTES.assignments}
              className="rounded-xl bg-sky-500 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-sky-400"
            >
              View offered assignments
            </Link>
            <Link
              to={TECHNICIAN_ROUTES.workOrders}
              className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-semibold text-slate-200 transition hover:border-slate-500 hover:text-white"
            >
              View my work orders
            </Link>
          </>
        }
      />

      {notice ? <Notice>{notice}</Notice> : null}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <SummaryCard
          label="Offered assignments"
          value={summary.offeredAssignmentTotal}
          note={summary.offeredTruncatedNote ?? undefined}
        />
        <SummaryCard
          label="Visible work orders"
          value={summary.assignedWorkOrderTotal}
          note={summary.workOrderTruncatedNote ?? undefined}
        />
        <SummaryCard
          label="In progress"
          value={summary.inProgressCount}
          note={summary.loadedStatusNote ?? undefined}
        />
        <SummaryCard
          label="Needs attention"
          value={summary.attentionCount}
          note={
            summary.loadedStatusNote
              ? 'Awaiting parts or escalated work orders loaded in this view.'
              : undefined
          }
        />
      </div>

      <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-white">
              Offered assignments
            </h2>
            <p className="mt-1 text-xs text-slate-500">
              Accept an offer to unlock work-order actions and service records.
            </p>
          </div>
          <Link
            to={TECHNICIAN_ROUTES.assignments}
            className="text-sm font-medium text-sky-300 hover:text-sky-200"
          >
            View all offers
          </Link>
        </div>

        {previews.offered.length === 0 ? (
          <div className="mt-4">
            <EmptyState
              title="No offered assignments"
              description="New work offers from the service team will appear here."
            />
          </div>
        ) : (
          <ul className="mt-4 grid gap-3">
            {previews.offered.map(({ assignment, workOrder }) => (
              <li
                key={assignment.id}
                className="rounded-xl border border-slate-800 bg-slate-950/40 p-4"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <AssignmentStatusBadge
                    status={assignment.assignment_status}
                  />
                  {workOrder ? (
                    <WorkOrderStatusBadge status={workOrder.status} />
                  ) : null}
                  <span className="text-xs text-slate-500">
                    Offered {formatDateTime(assignment.assigned_at)}
                  </span>
                </div>
                <p className="mt-2 text-sm font-medium text-white">
                  {workOrder?.title ??
                    `Work order ${assignment.work_order_id.slice(0, 8)}`}
                </p>
                <div className="mt-3 flex flex-wrap items-center gap-3">
                  <Link
                    to={technicianWorkOrderPath(assignment.work_order_id)}
                    className="text-sm font-medium text-sky-300 hover:text-sky-200"
                  >
                    View work order
                  </Link>
                </div>
                <div className="mt-3">
                  <AssignmentActions
                    assignment={assignment}
                    onUpdated={(_updated, action) => {
                      setNotice(
                        action === 'accepted'
                          ? 'Assignment accepted. The work order is now in your work orders.'
                          : 'Assignment rejected. The service team can reassign it.',
                      )
                      reload()
                    }}
                  />
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-base font-semibold text-white">
              Active work orders
            </h2>
            <Link
              to={TECHNICIAN_ROUTES.workOrders}
              className="text-sm font-medium text-sky-300 hover:text-sky-200"
            >
              View all
            </Link>
          </div>

          {previews.active.length === 0 ? (
            <p className="mt-4 text-sm text-slate-400">
              No active work orders in this view.
            </p>
          ) : (
            <ul className="mt-4 grid gap-2">
              {previews.active.map((workOrder) => (
                <li key={workOrder.id}>
                  <Link
                    to={technicianWorkOrderPath(workOrder.id)}
                    className="block rounded-xl border border-slate-800 bg-slate-950/40 p-3 transition hover:border-sky-500/40"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <WorkOrderStatusBadge status={workOrder.status} />
                      <PriorityBadge priority={workOrder.priority} />
                    </div>
                    <p className="mt-2 line-clamp-1 text-sm font-medium text-slate-100">
                      {workOrder.title}
                    </p>
                    <p className="mt-1 text-xs text-slate-500">
                      Updated {formatDateTime(workOrder.updated_at)}
                    </p>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-base font-semibold text-white">
              Recently completed
            </h2>
            <Link
              to={TECHNICIAN_ROUTES.workOrders}
              className="text-sm font-medium text-sky-300 hover:text-sky-200"
            >
              View all
            </Link>
          </div>

          {previews.completed.length === 0 ? (
            <p className="mt-4 text-sm text-slate-400">
              No completed work orders in this view.
            </p>
          ) : (
            <ul className="mt-4 grid gap-2">
              {previews.completed.map((workOrder) => (
                <li key={workOrder.id}>
                  <Link
                    to={technicianWorkOrderPath(workOrder.id)}
                    className="block rounded-xl border border-slate-800 bg-slate-950/40 p-3 transition hover:border-sky-500/40"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <WorkOrderStatusBadge status={workOrder.status} />
                      <span className="text-xs text-slate-500">
                        {formatDateTime(workOrder.updated_at)}
                      </span>
                    </div>
                    <p className="mt-2 line-clamp-1 text-sm font-medium text-slate-100">
                      {workOrder.title}
                    </p>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <p className="text-xs leading-5 text-slate-500">
        Summary totals come from the API. Status counts are qualified when only
        part of the list is loaded. Technician views do not expose customer
        profiles or equipment details; use the work-order identifiers when
        coordinating with the service team.
      </p>
    </div>
  )
}
