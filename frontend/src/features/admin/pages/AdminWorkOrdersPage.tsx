import { useState } from 'react'
import { Link } from 'react-router-dom'
import { EmptyState } from '../../../components/EmptyState'
import { ErrorScreen } from '../../../components/ErrorScreen'
import { FormField, inputClassName } from '../../../components/FormField'
import { LoadingScreen } from '../../../components/LoadingScreen'
import { PageHeader } from '../../../components/PageHeader'
import { useApiClient } from '../../../lib/api/api-client-context'
import { apiErrorMessage } from '../../../lib/api/errors'
import {
  PRIORITIES,
  type Priority,
  type WorkOrderStatus,
} from '../../../lib/api/types'
import { formatDateTime } from '../../../lib/format'
import { useAsyncData } from '../../../lib/hooks/use-async-data'
import { PriorityBadge } from '../../complaints/components/ComplaintBadges'
import { priorityLabel } from '../../complaints/labels'
import { WorkOrderStatusBadge } from '../../technicians/components/TechnicianBadges'
import { workOrderStatusLabel } from '../../technicians/labels'
import { listAdminWorkOrders } from '../api'
import { AdminPagination } from '../components/AdminPagination'
import { ADMIN_WORK_ORDER_STATUSES } from '../labels'
import { ADMIN_ROUTES, adminWorkOrderPath } from '../routes'

const PAGE_SIZE = 20

export function AdminWorkOrdersPage() {
  const apiClient = useApiClient()
  const [offset, setOffset] = useState(0)
  const [status, setStatus] = useState<WorkOrderStatus | ''>('')
  const [priority, setPriority] = useState<Priority | ''>('')

  const { data, error, isLoading, reload } = useAsyncData(
    (signal) =>
      listAdminWorkOrders(
        apiClient,
        {
          status: status || undefined,
          priority: priority || undefined,
          limit: PAGE_SIZE,
          offset,
        },
        signal,
      ),
    [apiClient, offset, status, priority],
  )

  return (
    <div className="grid gap-6">
      <PageHeader
        eyebrow="Administrator"
        title="Work orders"
        description="Track work-order state, edit editable fields, and coordinate assignments."
      />

      <section className="grid gap-4 rounded-2xl border border-slate-800 bg-slate-900/60 p-5 sm:grid-cols-2">
        <FormField id="admin-work-order-status-filter" label="Status">
          <select
            id="admin-work-order-status-filter"
            className={inputClassName}
            value={status}
            onChange={(event) => {
              setOffset(0)
              setStatus(event.target.value as WorkOrderStatus | '')
            }}
          >
            <option value="">All statuses</option>
            {ADMIN_WORK_ORDER_STATUSES.map((value) => (
              <option key={value} value={value}>
                {workOrderStatusLabel(value)}
              </option>
            ))}
          </select>
        </FormField>
        <FormField id="admin-work-order-priority-filter" label="Priority">
          <select
            id="admin-work-order-priority-filter"
            className={inputClassName}
            value={priority}
            onChange={(event) => {
              setOffset(0)
              setPriority(event.target.value as Priority | '')
            }}
          >
            <option value="">All priorities</option>
            {PRIORITIES.map((value) => (
              <option key={value} value={value}>
                {priorityLabel(value)}
              </option>
            ))}
          </select>
        </FormField>
      </section>

      {isLoading ? (
        <LoadingScreen label="Loading work orders..." />
      ) : error || !data ? (
        <ErrorScreen
          message={apiErrorMessage(error, 'Unable to load work orders.')}
          onRetry={reload}
        />
      ) : data.items.length === 0 ? (
        <EmptyState
          title="No work orders match these filters"
          description="Adjust the filters or convert an eligible complaint."
          action={
            <Link
              to={ADMIN_ROUTES.complaints}
              className="inline-flex rounded-lg border border-slate-700 px-4 py-2 text-sm font-medium text-slate-200 transition hover:border-slate-500"
            >
              Review complaints
            </Link>
          }
        />
      ) : (
        <>
          <ul className="grid gap-3">
            {data.items.map((workOrder) => (
              <li key={workOrder.id}>
                <Link
                  to={adminWorkOrderPath(workOrder.id)}
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
                </Link>
              </li>
            ))}
          </ul>
          <AdminPagination
            offset={offset}
            pageSize={PAGE_SIZE}
            total={data.total}
            noun="work orders"
            onOffsetChange={setOffset}
          />
        </>
      )}
    </div>
  )
}
