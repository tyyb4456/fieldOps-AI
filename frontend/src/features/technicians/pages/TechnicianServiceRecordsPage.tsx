import { useState } from 'react'
import { Link } from 'react-router-dom'
import { EmptyState } from '../../../components/EmptyState'
import { ErrorScreen } from '../../../components/ErrorScreen'
import { LoadingScreen } from '../../../components/LoadingScreen'
import { PageHeader } from '../../../components/PageHeader'
import { useApiClient } from '../../../lib/api/api-client-context'
import { apiErrorMessage } from '../../../lib/api/errors'
import { formatDateTime } from '../../../lib/format'
import { useAsyncData } from '../../../lib/hooks/use-async-data'
import { listServiceRecords, listWorkOrders } from '../../work-orders/api'
import type { ServiceRecord, WorkOrder } from '../../work-orders/types'
import { WorkOrderStatusBadge } from '../components/TechnicianBadges'
import {
  TECHNICIAN_ROUTES,
  technicianServiceRecordPath,
  technicianWorkOrderPath,
} from '../routes'

const PAGE_SIZE = 12
const WORK_ORDER_LOOKUP_LIMIT = 100

interface ServiceRecordPageData {
  records: Awaited<ReturnType<typeof listServiceRecords>>
  workOrders: WorkOrder[]
}

export function TechnicianServiceRecordsPage() {
  const apiClient = useApiClient()
  const [offset, setOffset] = useState(0)

  const { data, error, isLoading, reload } =
    useAsyncData<ServiceRecordPageData>(
      async (signal) => {
        const [records, workOrders] = await Promise.all([
          listServiceRecords(
            apiClient,
            { limit: PAGE_SIZE, offset },
            signal,
          ),
          listWorkOrders(
            apiClient,
            { limit: WORK_ORDER_LOOKUP_LIMIT, offset: 0 },
            signal,
          ),
        ])
        return { records, workOrders: workOrders.items }
      },
      [apiClient, offset],
    )

  const workOrderById = new Map(
    (data?.workOrders ?? []).map((workOrder) => [workOrder.id, workOrder]),
  )

  const page = Math.floor(offset / PAGE_SIZE) + 1
  const totalPages = data
    ? Math.max(1, Math.ceil(data.records.total / PAGE_SIZE))
    : 1

  function recordSummary(record: ServiceRecord): string {
    return (
      record.work_performed ??
      record.findings ??
      'No findings or work performed were recorded.'
    )
  }

  return (
    <div className="grid gap-6">
      <PageHeader
        eyebrow="Technician service records"
        title="Service records"
        description="Review the service activity you recorded across your visible work orders."
        actions={
          <Link
            to={TECHNICIAN_ROUTES.workOrders}
            className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-semibold text-slate-200 transition hover:border-slate-500 hover:text-white"
          >
            My work orders
          </Link>
        }
      />

      {isLoading ? (
        <LoadingScreen label="Loading your service records..." />
      ) : error || !data ? (
        <ErrorScreen
          message={apiErrorMessage(
            error,
            'Unable to load your service records.',
          )}
          onRetry={reload}
        />
      ) : data.records.items.length === 0 ? (
        <EmptyState
          title="No service records"
          description="Service records you add to accepted work orders will appear here."
          action={
            <Link
              to={TECHNICIAN_ROUTES.workOrders}
              className="inline-flex rounded-lg bg-sky-500 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-sky-400"
            >
              Open my work orders
            </Link>
          }
        />
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
            <span>
              {data.records.total} service record
              {data.records.total === 1 ? '' : 's'}
            </span>
            <span>
              Page {page} of {totalPages}
            </span>
          </div>

          <ul className="grid gap-3">
            {data.records.items.map((record) => {
              const workOrder = workOrderById.get(record.work_order_id)
              return (
                <li
                  key={record.id}
                  className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    {workOrder ? (
                      <WorkOrderStatusBadge status={workOrder.status} />
                    ) : null}
                    <span className="text-xs text-slate-500">
                      Recorded {formatDateTime(record.recorded_at)}
                    </span>
                    <span className="text-xs text-slate-500">
                      {record.parts_used.length} part
                      {record.parts_used.length === 1 ? '' : 's'} used
                    </span>
                  </div>

                  <h2 className="mt-3 text-base font-semibold text-white">
                    {workOrder?.title ??
                      `Work order ${record.work_order_id.slice(0, 8)}`}
                  </h2>
                  <p className="mt-1 line-clamp-2 text-sm leading-6 text-slate-300">
                    {recordSummary(record)}
                  </p>

                  <div className="mt-4 flex flex-wrap items-center gap-4">
                    <Link
                      to={technicianServiceRecordPath(record.id)}
                      className="text-sm font-medium text-sky-300 hover:text-sky-200"
                    >
                      View service record
                    </Link>
                    <Link
                      to={technicianWorkOrderPath(record.work_order_id)}
                      className="text-sm font-medium text-slate-400 hover:text-slate-200"
                    >
                      Open work order
                    </Link>
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
              {Math.min(offset + data.records.items.length, data.records.total)}{' '}
              of {data.records.total}
            </span>
            <button
              type="button"
              onClick={() => setOffset(offset + PAGE_SIZE)}
              disabled={offset + PAGE_SIZE >= data.records.total}
              className="rounded-lg border border-slate-700 px-4 py-2 text-sm font-medium text-slate-200 transition hover:border-slate-500 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </>
      )}
    </div>
  )
}
