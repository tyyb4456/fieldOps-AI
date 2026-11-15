import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { EmptyState } from '../../../components/EmptyState'
import { ErrorScreen } from '../../../components/ErrorScreen'
import { Notice } from '../../../components/Feedback'
import { LoadingScreen } from '../../../components/LoadingScreen'
import { PageHeader } from '../../../components/PageHeader'
import { useApiClient } from '../../../lib/api/api-client-context'
import { apiErrorMessage } from '../../../lib/api/errors'
import { formatDateTime } from '../../../lib/format'
import { useAsyncData } from '../../../lib/hooks/use-async-data'
import { listAssignments } from '../../assignments/api'
import type { Assignment } from '../../assignments/types'
import { PriorityBadge } from '../../complaints/components/ComplaintBadges'
import { listWorkOrders } from '../../work-orders/api'
import type { WorkOrder } from '../../work-orders/types'
import { AssignmentActions } from '../components/AssignmentActions'
import {
  AssignmentStatusBadge,
  WorkOrderStatusBadge,
} from '../components/TechnicianBadges'
import { TECHNICIAN_ROUTES, technicianWorkOrderPath } from '../routes'

const PAGE_SIZE = 12
const WORK_ORDER_LOOKUP_LIMIT = 100

interface AssignmentPageData {
  assignments: Awaited<ReturnType<typeof listAssignments>>
  workOrders: WorkOrder[]
}

export function TechnicianAssignmentsPage() {
  const apiClient = useApiClient()
  const location = useLocation()
  const [offset, setOffset] = useState(0)
  const [notice, setNotice] = useState<string | null>(
    () => (location.state as { notice?: string } | null)?.notice ?? null,
  )

  const { data, error, isLoading, reload } = useAsyncData<AssignmentPageData>(
    async (signal) => {
      const [assignments, workOrders] = await Promise.all([
        listAssignments(
          apiClient,
          { status: 'offered', limit: PAGE_SIZE, offset },
          signal,
        ),
        listWorkOrders(
          apiClient,
          { limit: WORK_ORDER_LOOKUP_LIMIT, offset: 0 },
          signal,
        ),
      ])
      return { assignments, workOrders: workOrders.items }
    },
    [apiClient, offset],
  )

  const workOrderById = new Map(
    (data?.workOrders ?? []).map((workOrder) => [workOrder.id, workOrder]),
  )

  function handleUpdated(_assignment: Assignment, action: 'accepted' | 'rejected') {
    setNotice(
      action === 'accepted'
        ? 'Assignment accepted. The work order is now in your work orders.'
        : 'Assignment rejected. The service team can reassign it.',
    )
    reload()
  }

  const page = Math.floor(offset / PAGE_SIZE) + 1
  const totalPages = data
    ? Math.max(1, Math.ceil(data.assignments.total / PAGE_SIZE))
    : 1

  return (
    <div className="grid gap-6">
      <PageHeader
        eyebrow="Technician assignments"
        title="Offered assignments"
        description="Review new work offers, check the work-order summary, and accept or reject the assignment."
        actions={
          <Link
            to={TECHNICIAN_ROUTES.workOrders}
            className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-semibold text-slate-200 transition hover:border-slate-500 hover:text-white"
          >
            My work orders
          </Link>
        }
      />

      {notice ? <Notice>{notice}</Notice> : null}

      {isLoading ? (
        <LoadingScreen label="Loading offered assignments..." />
      ) : error || !data ? (
        <ErrorScreen
          message={apiErrorMessage(
            error,
            'Unable to load your offered assignments.',
          )}
          onRetry={reload}
        />
      ) : data.assignments.items.length === 0 ? (
        <EmptyState
          title="No offered assignments"
          description="When the service team offers you a work order, it will appear here for review."
          action={
            <Link
              to={TECHNICIAN_ROUTES.workOrders}
              className="inline-flex rounded-lg border border-slate-700 px-4 py-2 text-sm font-medium text-slate-200 transition hover:border-slate-500"
            >
              View my work orders
            </Link>
          }
        />
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
            <span>
              {data.assignments.total} offered assignment
              {data.assignments.total === 1 ? '' : 's'}
            </span>
            <span>
              Page {page} of {totalPages}
            </span>
          </div>

          <ul className="grid gap-3">
            {data.assignments.items.map((assignment) => {
              const workOrder = workOrderById.get(assignment.work_order_id)
              return (
                <li
                  key={assignment.id}
                  className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <AssignmentStatusBadge
                      status={assignment.assignment_status}
                    />
                    {workOrder ? (
                      <WorkOrderStatusBadge status={workOrder.status} />
                    ) : null}
                    {workOrder ? (
                      <PriorityBadge priority={workOrder.priority} />
                    ) : null}
                    <span className="text-xs text-slate-500">
                      Offered {formatDateTime(assignment.assigned_at)}
                    </span>
                  </div>

                  <h2 className="mt-3 text-base font-semibold text-white">
                    {workOrder?.title ??
                      `Work order ${assignment.work_order_id.slice(0, 8)}`}
                  </h2>
                  {workOrder ? (
                    <p className="mt-1 line-clamp-2 text-sm leading-6 text-slate-300">
                      {workOrder.description}
                    </p>
                  ) : (
                    <p className="mt-1 text-sm text-slate-400">
                      The work-order summary is not available in the loaded
                      list. Open the work order to review it.
                    </p>
                  )}

                  <dl className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-xs text-slate-500">
                    <div className="flex gap-1">
                      <dt>Equipment:</dt>
                      <dd className="font-mono text-slate-300">
                        {workOrder?.equipment_id ??
                          assignment.work_order_id.slice(0, 8)}
                      </dd>
                    </div>
                    {workOrder ? (
                      <div className="flex gap-1">
                        <dt>Updated:</dt>
                        <dd className="text-slate-300">
                          {formatDateTime(workOrder.updated_at)}
                        </dd>
                      </div>
                    ) : null}
                  </dl>

                  <div className="mt-4 flex flex-wrap items-center justify-between gap-4">
                    <Link
                      to={technicianWorkOrderPath(assignment.work_order_id)}
                      className="text-sm font-medium text-sky-300 hover:text-sky-200"
                    >
                      View work order
                    </Link>
                    <AssignmentActions
                      assignment={assignment}
                      onUpdated={handleUpdated}
                    />
                  </div>
                </li>
              )
            })}
          </ul>

          <div className="flex items-center justify-between gap-3">
            <button
              type="button"
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              disabled={offset === 0}
              className="rounded-lg border border-slate-700 px-4 py-2 text-sm font-medium text-slate-200 transition hover:border-slate-500 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Previous
            </button>
            <span className="text-xs text-slate-500">
              Showing {offset + 1}-
              {Math.min(
                offset + data.assignments.items.length,
                data.assignments.total,
              )}{' '}
              of {data.assignments.total}
            </span>
            <button
              type="button"
              onClick={() => setOffset(offset + PAGE_SIZE)}
              disabled={offset + PAGE_SIZE >= data.assignments.total}
              className="rounded-lg border border-slate-700 px-4 py-2 text-sm font-medium text-slate-200 transition hover:border-slate-500 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </>
      )}

      <p className="text-xs leading-5 text-slate-500">
        Accepting or rejecting an offer is only possible while the assignment is
        offered and the work order is assigned. The API enforces the final
        permission and lifecycle checks.
      </p>
    </div>
  )
}
