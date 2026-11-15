import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { EmptyState } from '../../../components/EmptyState'
import { ErrorScreen } from '../../../components/ErrorScreen'
import { inputClassName } from '../../../components/FormField'
import { LoadingScreen } from '../../../components/LoadingScreen'
import { PageHeader } from '../../../components/PageHeader'
import { useApiClient } from '../../../lib/api/api-client-context'
import { apiErrorMessage } from '../../../lib/api/errors'
import type { WorkOrderStatus } from '../../../lib/api/types'
import { formatDateTime } from '../../../lib/format'
import { useAsyncData } from '../../../lib/hooks/use-async-data'
import { PriorityBadge } from '../../complaints/components/ComplaintBadges'
import { listWorkOrders } from '../../work-orders/api'
import { WorkOrderStatusBadge } from '../components/TechnicianBadges'
import {
  TECHNICIAN_FILTERABLE_WORK_ORDER_STATUSES,
  workOrderStatusLabel,
} from '../labels'
import { TECHNICIAN_ROUTES, technicianWorkOrderPath } from '../routes'

const PAGE_SIZE = 12

export function TechnicianWorkOrdersPage() {
  const apiClient = useApiClient()
  const [draftStatus, setDraftStatus] = useState<WorkOrderStatus | ''>('')
  const [status, setStatus] = useState<WorkOrderStatus | ''>('')
  const [offset, setOffset] = useState(0)

  const { data, error, isLoading, reload } = useAsyncData(
    (signal) =>
      listWorkOrders(
        apiClient,
        {
          status: status || undefined,
          limit: PAGE_SIZE,
          offset,
        },
        signal,
      ),
    [apiClient, status, offset],
  )

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setOffset(0)
    setStatus(draftStatus)
  }

  function clearFilters() {
    setDraftStatus('')
    setStatus('')
    setOffset(0)
  }

  const hasActiveFilters = status !== ''
  const page = Math.floor(offset / PAGE_SIZE) + 1
  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1

  return (
    <div className="grid gap-6">
      <PageHeader
        eyebrow="Technician work orders"
        title="My work orders"
        description="Follow every work order offered to you or accepted by you, from assignment through completion."
        actions={
          <Link
            to={TECHNICIAN_ROUTES.assignments}
            className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-semibold text-slate-200 transition hover:border-slate-500 hover:text-white"
          >
            Offered assignments
          </Link>
        }
      />

      <form
        onSubmit={applyFilters}
        className="grid gap-4 rounded-2xl border border-slate-800 bg-slate-900/60 p-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end"
      >
        <div className="grid gap-1.5">
          <label
            htmlFor="technician-work-order-status"
            className="text-sm font-medium text-slate-200"
          >
            Status
          </label>
          <select
            id="technician-work-order-status"
            className={inputClassName}
            value={draftStatus}
            onChange={(event) =>
              setDraftStatus(event.target.value as WorkOrderStatus | '')
            }
          >
            <option value="">All statuses</option>
            {TECHNICIAN_FILTERABLE_WORK_ORDER_STATUSES.map((option) => (
              <option key={option} value={option}>
                {workOrderStatusLabel(option)}
              </option>
            ))}
          </select>
        </div>

        <div className="flex gap-2">
          <button
            type="submit"
            className="rounded-xl bg-slate-700 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-600"
          >
            Apply filters
          </button>
          {hasActiveFilters ? (
            <button
              type="button"
              onClick={clearFilters}
              className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-medium text-slate-200 transition hover:border-slate-500"
            >
              Clear
            </button>
          ) : null}
        </div>
      </form>

      {isLoading ? (
        <LoadingScreen label="Loading your work orders..." />
      ) : error ? (
        <ErrorScreen
          message={apiErrorMessage(error, 'Unable to load your work orders.')}
          onRetry={reload}
        />
      ) : !data ? null : data.items.length === 0 ? (
        <EmptyState
          title={
            hasActiveFilters
              ? 'No work orders match this filter'
              : 'No work orders yet'
          }
          description={
            hasActiveFilters
              ? 'Try a different status or clear the filter.'
              : 'Accepted assignments and new offers will appear here.'
          }
          action={
            hasActiveFilters ? (
              <button
                type="button"
                onClick={clearFilters}
                className="rounded-lg border border-slate-700 px-4 py-2 text-sm font-medium text-slate-200 transition hover:border-slate-500"
              >
                Clear filter
              </button>
            ) : (
              <Link
                to={TECHNICIAN_ROUTES.assignments}
                className="inline-flex rounded-lg bg-sky-500 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-sky-400"
              >
                Review offered assignments
              </Link>
            )
          }
        />
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
            <span>
              {data.total} work order{data.total === 1 ? '' : 's'}
            </span>
            <span>
              Page {page} of {totalPages}
            </span>
          </div>

          <ul className="grid gap-3">
            {data.items.map((workOrder) => (
              <li key={workOrder.id}>
                <Link
                  to={technicianWorkOrderPath(workOrder.id)}
                  className="block rounded-2xl border border-slate-800 bg-slate-900/60 p-5 transition hover:border-sky-500/40"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <WorkOrderStatusBadge status={workOrder.status} />
                    <PriorityBadge priority={workOrder.priority} />
                    <span className="text-xs text-slate-500">
                      Updated {formatDateTime(workOrder.updated_at)}
                    </span>
                  </div>
                  <h2 className="mt-3 text-base font-semibold text-white">
                    {workOrder.title}
                  </h2>
                  <p className="mt-1 line-clamp-2 text-sm leading-6 text-slate-300">
                    {workOrder.description}
                  </p>
                  <dl className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-xs text-slate-500">
                    <div className="flex gap-1">
                      <dt>Equipment:</dt>
                      <dd className="font-mono text-slate-300">
                        {workOrder.equipment_id}
                      </dd>
                    </div>
                    <div className="flex gap-1">
                      <dt>Complaint:</dt>
                      <dd className="font-mono text-slate-300">
                        {workOrder.complaint_id}
                      </dd>
                    </div>
                  </dl>
                </Link>
              </li>
            ))}
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
              {Math.min(offset + data.items.length, data.total)} of {data.total}
            </span>
            <button
              type="button"
              onClick={() => setOffset(offset + PAGE_SIZE)}
              disabled={offset + PAGE_SIZE >= data.total}
              className="rounded-lg border border-slate-700 px-4 py-2 text-sm font-medium text-slate-200 transition hover:border-slate-500 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </>
      )}

      <p className="text-xs leading-5 text-slate-500">
        Only work orders with an offered or accepted assignment are visible to
        technicians. Customer and equipment details are not included in the
        technician work-order response.
      </p>
    </div>
  )
}
