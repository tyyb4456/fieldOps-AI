import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { EmptyState } from '../../../components/EmptyState'
import { ErrorScreen } from '../../../components/ErrorScreen'
import { FormField, inputClassName } from '../../../components/FormField'
import { LoadingScreen } from '../../../components/LoadingScreen'
import { PageHeader } from '../../../components/PageHeader'
import { useApiClient } from '../../../lib/api/api-client-context'
import { apiErrorMessage } from '../../../lib/api/errors'
import type { ComplaintStatus } from '../../../lib/api/types'
import { formatDateTime } from '../../../lib/format'
import { useAsyncData } from '../../../lib/hooks/use-async-data'
import {
  ComplaintStatusBadge,
  PriorityBadge,
} from '../../complaints/components/ComplaintBadges'
import { complaintStatusLabel } from '../../complaints/labels'
import { listAdminComplaints } from '../api'
import { AdminPagination } from '../components/AdminPagination'
import { ADMIN_COMPLAINT_STATUS_FILTERS } from '../labels'
import { ADMIN_ROUTES, adminComplaintPath } from '../routes'

const PAGE_SIZE = 20

export function AdminComplaintsPage() {
  const apiClient = useApiClient()
  const [offset, setOffset] = useState(0)
  const [status, setStatus] = useState<ComplaintStatus | ''>('')
  const [customerInput, setCustomerInput] = useState('')
  const [customerId, setCustomerId] = useState('')

  const { data, error, isLoading, reload } = useAsyncData(
    (signal) =>
      listAdminComplaints(
        apiClient,
        {
          status: status || undefined,
          customer_id: customerId || undefined,
          limit: PAGE_SIZE,
          offset,
        },
        signal,
      ),
    [apiClient, offset, status, customerId],
  )

  function applyCustomerFilter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setOffset(0)
    setCustomerId(customerInput.trim())
  }

  return (
    <div className="grid gap-6">
      <PageHeader
        eyebrow="Administrator"
        title="Complaints"
        description="Review incoming complaints, inspect their history, and convert eligible complaints into work orders."
      />

      <section className="grid gap-4 rounded-2xl border border-slate-800 bg-slate-900/60 p-5 sm:grid-cols-2">
        <FormField id="admin-complaint-status-filter" label="Status">
          <select
            id="admin-complaint-status-filter"
            className={inputClassName}
            value={status}
            onChange={(event) => {
              setOffset(0)
              setStatus(event.target.value as ComplaintStatus | '')
            }}
          >
            <option value="">All statuses</option>
            {ADMIN_COMPLAINT_STATUS_FILTERS.map((value) => (
              <option key={value} value={value}>
                {complaintStatusLabel(value)}
              </option>
            ))}
          </select>
        </FormField>

        <form onSubmit={applyCustomerFilter} className="grid gap-2">
          <FormField
            id="admin-complaint-customer-filter"
            label="Customer ID"
            hint="Filter by the exact customer identifier."
          >
            <div className="flex gap-2">
              <input
                id="admin-complaint-customer-filter"
                className={inputClassName}
                value={customerInput}
                onChange={(event) => setCustomerInput(event.target.value)}
                placeholder="00000000-0000-0000-0000-000000000000"
              />
              <button
                type="submit"
                className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-medium text-slate-200 transition hover:border-slate-500"
              >
                Apply
              </button>
            </div>
          </FormField>
        </form>
      </section>

      {isLoading ? (
        <LoadingScreen label="Loading complaints..." />
      ) : error || !data ? (
        <ErrorScreen
          message={apiErrorMessage(error, 'Unable to load complaints.')}
          onRetry={reload}
        />
      ) : data.items.length === 0 ? (
        <EmptyState
          title="No complaints match these filters"
          description="Adjust the status or customer filter to find complaints."
        />
      ) : (
        <>
          <ul className="grid gap-3">
            {data.items.map((complaint) => (
              <li key={complaint.id}>
                <Link
                  to={adminComplaintPath(complaint.id)}
                  className="block rounded-2xl border border-slate-800 bg-slate-900/60 p-5 transition hover:border-sky-500/40"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <ComplaintStatusBadge status={complaint.status} />
                    <PriorityBadge priority={complaint.priority} />
                    <span className="text-xs text-slate-500">
                      {formatDateTime(complaint.created_at)}
                    </span>
                  </div>
                  <p className="mt-3 line-clamp-2 text-sm leading-6 text-slate-100">
                    {complaint.description}
                  </p>
                  <p className="mt-2 font-mono text-xs text-slate-500">
                    Customer {complaint.customer_id}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
          <AdminPagination
            offset={offset}
            pageSize={PAGE_SIZE}
            total={data.total}
            noun="complaints"
            onOffsetChange={setOffset}
          />
        </>
      )}

      <div className="flex flex-wrap gap-2">
        <Link
          to={ADMIN_ROUTES.dashboard}
          className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-medium text-slate-200 transition hover:border-slate-500"
        >
          Back to dashboard
        </Link>
        <Link
          to={ADMIN_ROUTES.workOrders}
          className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-medium text-slate-200 transition hover:border-slate-500"
        >
          Work orders
        </Link>
      </div>
    </div>
  )
}
