import { useState } from 'react'
import { Link } from 'react-router-dom'
import { EmptyState } from '../../../components/EmptyState'
import { ErrorScreen } from '../../../components/ErrorScreen'
import { FormError, Notice } from '../../../components/Feedback'
import { FormField, inputClassName } from '../../../components/FormField'
import { LoadingScreen } from '../../../components/LoadingScreen'
import { PageHeader } from '../../../components/PageHeader'
import { useApiClient } from '../../../lib/api/api-client-context'
import { apiErrorMessage } from '../../../lib/api/errors'
import type { AssignmentStatus } from '../../../lib/api/types'
import { formatDateTime } from '../../../lib/format'
import { useAsyncData } from '../../../lib/hooks/use-async-data'
import { AssignmentStatusBadge } from '../../technicians/components/TechnicianBadges'
import { ASSIGNMENT_STATUS_LABELS } from '../../technicians/labels'
import { listAdminAssignments, withdrawAdminAssignment } from '../api'
import { AdminPagination } from '../components/AdminPagination'
import { adminAssignmentErrorMessage } from '../errors'
import { ADMIN_ROUTES, adminWorkOrderPath } from '../routes'

const PAGE_SIZE = 20
const ACTIVE_STATUSES: readonly AssignmentStatus[] = ['offered', 'accepted']

export function AdminAssignmentsPage() {
  const apiClient = useApiClient()
  const [offset, setOffset] = useState(0)
  const [status, setStatus] = useState<AssignmentStatus | ''>('')
  const [notice, setNotice] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [withdrawingId, setWithdrawingId] = useState<string | null>(null)

  const { data, error, isLoading, reload } = useAsyncData(
    (signal) =>
      listAdminAssignments(
        apiClient,
        {
          status: status || undefined,
          limit: PAGE_SIZE,
          offset,
        },
        signal,
      ),
    [apiClient, offset, status],
  )

  async function withdraw(assignmentId: string) {
    if (!window.confirm('Withdraw this active assignment?')) {
      return
    }
    setWithdrawingId(assignmentId)
    setActionError(null)
    try {
      await withdrawAdminAssignment(apiClient, assignmentId)
      setNotice('Assignment withdrawn.')
      reload()
    } catch (caught) {
      setActionError(adminAssignmentErrorMessage(caught))
    } finally {
      setWithdrawingId(null)
    }
  }

  return (
    <div className="grid gap-6">
      <PageHeader
        eyebrow="Administrator"
        title="Assignments"
        description="Track offers and accepted assignments across work orders. Withdraw an active assignment to reassign the work."
      />

      {notice ? <Notice>{notice}</Notice> : null}
      <FormError message={actionError} />

      <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <FormField id="admin-assignment-status-filter" label="Status">
          <select
            id="admin-assignment-status-filter"
            className={inputClassName}
            value={status}
            onChange={(event) => {
              setOffset(0)
              setStatus(event.target.value as AssignmentStatus | '')
            }}
          >
            <option value="">All statuses</option>
            {(
              Object.keys(ASSIGNMENT_STATUS_LABELS) as AssignmentStatus[]
            ).map((value) => (
              <option key={value} value={value}>
                {ASSIGNMENT_STATUS_LABELS[value]}
              </option>
            ))}
          </select>
        </FormField>
      </section>

      {isLoading ? (
        <LoadingScreen label="Loading assignments..." />
      ) : error || !data ? (
        <ErrorScreen
          message={apiErrorMessage(error, 'Unable to load assignments.')}
          onRetry={reload}
        />
      ) : data.items.length === 0 ? (
        <EmptyState
          title="No assignments match these filters"
          description="Offer a work order to a technician from its detail page."
        />
      ) : (
        <>
          <ul className="grid gap-3">
            {data.items.map((assignment) => (
              <li
                key={assignment.id}
                className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <AssignmentStatusBadge
                    status={assignment.assignment_status}
                  />
                  <span className="text-xs text-slate-500">
                    Offered {formatDateTime(assignment.assigned_at)}
                  </span>
                  {assignment.accepted_at ? (
                    <span className="text-xs text-slate-500">
                      Accepted {formatDateTime(assignment.accepted_at)}
                    </span>
                  ) : null}
                </div>
                <p className="mt-3 font-mono text-xs text-slate-500">
                  Technician {assignment.technician_id}
                </p>
                <p className="mt-1 font-mono text-xs text-slate-500">
                  Work order {assignment.work_order_id}
                </p>
                <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                  <Link
                    to={adminWorkOrderPath(assignment.work_order_id)}
                    className="text-sm font-medium text-sky-300 hover:text-sky-200"
                  >
                    View work order
                  </Link>
                  {ACTIVE_STATUSES.includes(
                    assignment.assignment_status,
                  ) ? (
                    <button
                      type="button"
                      onClick={() => void withdraw(assignment.id)}
                      disabled={withdrawingId !== null}
                      className="rounded-lg border border-rose-500/40 px-3 py-2 text-xs font-medium text-rose-200 transition hover:bg-rose-500/10 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {withdrawingId === assignment.id
                        ? 'Withdrawing...'
                        : 'Withdraw assignment'}
                    </button>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
          <AdminPagination
            offset={offset}
            pageSize={PAGE_SIZE}
            total={data.total}
            noun="assignments"
            onOffsetChange={setOffset}
          />
        </>
      )}

      <Link
        to={ADMIN_ROUTES.workOrders}
        className="w-fit rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-medium text-slate-200 transition hover:border-slate-500"
      >
        Manage work orders
      </Link>
    </div>
  )
}
