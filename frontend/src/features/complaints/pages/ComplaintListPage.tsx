import { useState, type FormEvent } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { EmptyState } from '../../../components/EmptyState'
import { ErrorScreen } from '../../../components/ErrorScreen'
import { FormError, Notice } from '../../../components/Feedback'
import { inputClassName } from '../../../components/FormField'
import { LoadingScreen } from '../../../components/LoadingScreen'
import { PageHeader } from '../../../components/PageHeader'
import { useApiClient } from '../../../lib/api/api-client-context'
import { apiErrorMessage } from '../../../lib/api/errors'
import {
  COMPLAINT_STATUSES,
  type ComplaintStatus,
} from '../../../lib/api/types'
import { formatDateTime } from '../../../lib/format'
import { useAsyncData } from '../../../lib/hooks/use-async-data'
import {
  CUSTOMER_ROUTES,
  customerComplaintPath,
} from '../../customers/routes'
import { listEquipment } from '../../equipment/api'
import { listComplaints } from '../api'
import {
  ComplaintStatusBadge,
  PriorityBadge,
} from '../components/ComplaintBadges'
import { complaintStatusLabel } from '../labels'

const PAGE_SIZE = 12

interface ComplaintFilters {
  status: ComplaintStatus | ''
  equipmentId: string
  createdFrom: string
  createdTo: string
}

const EMPTY_FILTERS: ComplaintFilters = {
  status: '',
  equipmentId: '',
  createdFrom: '',
  createdTo: '',
}

export function ComplaintListPage() {
  const apiClient = useApiClient()
  const location = useLocation()
  const notice = (location.state as { notice?: string } | null)?.notice
  const [draft, setDraft] = useState<ComplaintFilters>(EMPTY_FILTERS)
  const [filters, setFilters] = useState<ComplaintFilters>(EMPTY_FILTERS)
  const [offset, setOffset] = useState(0)
  const [rangeError, setRangeError] = useState<string | null>(null)

  const equipmentOptions = useAsyncData(
    (signal) => listEquipment(apiClient, { limit: 100 }, signal),
    [apiClient],
  )

  const complaints = useAsyncData(
    (signal) =>
      listComplaints(
        apiClient,
        {
          status: filters.status || undefined,
          equipment_id: filters.equipmentId || undefined,
          created_from: filters.createdFrom || undefined,
          created_to: filters.createdTo || undefined,
          limit: PAGE_SIZE,
          offset,
        },
        signal,
      ),
    [
      apiClient,
      filters.status,
      filters.equipmentId,
      filters.createdFrom,
      filters.createdTo,
      offset,
    ],
  )

  const equipmentById = new Map(
    (equipmentOptions.data?.items ?? []).map((item) => [
      item.id,
      `${item.manufacturer} ${item.model}`,
    ]),
  )

  function updateDraft<K extends keyof ComplaintFilters>(
    field: K,
    value: ComplaintFilters[K],
  ) {
    setDraft((current) => ({ ...current, [field]: value }))
  }

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (
      draft.createdFrom &&
      draft.createdTo &&
      draft.createdFrom > draft.createdTo
    ) {
      setRangeError('The start date must be on or before the end date.')
      return
    }

    setRangeError(null)
    setOffset(0)
    setFilters(draft)
  }

  function clearFilters() {
    setDraft(EMPTY_FILTERS)
    setFilters(EMPTY_FILTERS)
    setOffset(0)
    setRangeError(null)
  }

  const hasActiveFilters =
    filters.status !== '' ||
    filters.equipmentId !== '' ||
    filters.createdFrom !== '' ||
    filters.createdTo !== ''

  const page = Math.floor(offset / PAGE_SIZE) + 1
  const totalPages = complaints.data
    ? Math.max(1, Math.ceil(complaints.data.total / PAGE_SIZE))
    : 1

  return (
    <div className="grid gap-6">
      <PageHeader
        eyebrow="My complaints"
        title="Service complaints"
        description="Track every problem you have reported and its current status."
        actions={
          <Link
            to={CUSTOMER_ROUTES.newComplaint}
            className="rounded-xl bg-sky-500 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-sky-400"
          >
            Report a problem
          </Link>
        }
      />

      {notice ? <Notice>{notice}</Notice> : null}

      <form
        onSubmit={applyFilters}
        className="grid gap-4 rounded-2xl border border-slate-800 bg-slate-900/60 p-4 sm:grid-cols-2 lg:grid-cols-5 lg:items-end"
      >
        <div className="grid gap-1.5">
          <label
            htmlFor="complaint-status-filter"
            className="text-sm font-medium text-slate-200"
          >
            Status
          </label>
          <select
            id="complaint-status-filter"
            className={inputClassName}
            value={draft.status}
            onChange={(event) =>
              updateDraft(
                'status',
                event.target.value as ComplaintStatus | '',
              )
            }
          >
            <option value="">All statuses</option>
            {COMPLAINT_STATUSES.map((status) => (
              <option key={status} value={status}>
                {complaintStatusLabel(status)}
              </option>
            ))}
          </select>
        </div>

        <div className="grid gap-1.5">
          <label
            htmlFor="complaint-equipment-filter"
            className="text-sm font-medium text-slate-200"
          >
            Equipment
          </label>
          <select
            id="complaint-equipment-filter"
            className={inputClassName}
            value={draft.equipmentId}
            disabled={equipmentOptions.isLoading}
            onChange={(event) => updateDraft('equipmentId', event.target.value)}
          >
            <option value="">All equipment</option>
            {(equipmentOptions.data?.items ?? []).map((item) => (
              <option key={item.id} value={item.id}>
                {item.manufacturer} {item.model}
              </option>
            ))}
          </select>
        </div>

        <div className="grid gap-1.5">
          <label
            htmlFor="complaint-from-filter"
            className="text-sm font-medium text-slate-200"
          >
            Created from
          </label>
          <input
            id="complaint-from-filter"
            type="date"
            className={inputClassName}
            value={draft.createdFrom}
            onChange={(event) => updateDraft('createdFrom', event.target.value)}
          />
        </div>

        <div className="grid gap-1.5">
          <label
            htmlFor="complaint-to-filter"
            className="text-sm font-medium text-slate-200"
          >
            Created to
          </label>
          <input
            id="complaint-to-filter"
            type="date"
            className={inputClassName}
            value={draft.createdTo}
            onChange={(event) => updateDraft('createdTo', event.target.value)}
          />
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

        {rangeError ? (
          <div className="sm:col-span-2 lg:col-span-5">
            <FormError message={rangeError} />
          </div>
        ) : null}

        {equipmentOptions.error ? (
          <p className="text-xs text-amber-300 sm:col-span-2 lg:col-span-5">
            Equipment filter options could not be loaded. Other filters still
            work.
          </p>
        ) : null}
      </form>

      {complaints.isLoading ? (
        <LoadingScreen label="Loading complaints..." />
      ) : complaints.error ? (
        <ErrorScreen
          message={apiErrorMessage(
            complaints.error,
            'Unable to load your complaints.',
          )}
          onRetry={complaints.reload}
        />
      ) : !complaints.data ? null : complaints.data.items.length === 0 ? (
        <EmptyState
          title={
            hasActiveFilters ? 'No complaints match these filters' : 'No complaints yet'
          }
          description={
            hasActiveFilters
              ? 'Try widening the date range or clearing the filters.'
              : 'Report a problem and it will appear here with its current status.'
          }
          action={
            hasActiveFilters ? (
              <button
                type="button"
                onClick={clearFilters}
                className="rounded-lg border border-slate-700 px-4 py-2 text-sm font-medium text-slate-200 transition hover:border-slate-500"
              >
                Clear filters
              </button>
            ) : (
              <Link
                to={CUSTOMER_ROUTES.newComplaint}
                className="inline-flex rounded-lg bg-sky-500 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-sky-400"
              >
                Submit a complaint
              </Link>
            )
          }
        />
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
            <span>
              {complaints.data.total} complaint
              {complaints.data.total === 1 ? '' : 's'}
            </span>
            <span>
              Page {page} of {totalPages}
            </span>
          </div>

          <ul className="grid gap-3">
            {complaints.data.items.map((complaint) => (
              <li key={complaint.id}>
                <Link
                  to={customerComplaintPath(complaint.id)}
                  className="block rounded-2xl border border-slate-800 bg-slate-900/60 p-5 transition hover:border-sky-500/40"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <ComplaintStatusBadge status={complaint.status} />
                    <PriorityBadge priority={complaint.priority} />
                    <span className="text-xs text-slate-500">
                      {formatDateTime(complaint.created_at)}
                    </span>
                  </div>
                  <p className="mt-3 line-clamp-2 text-sm leading-6 text-slate-200">
                    {complaint.description}
                  </p>
                  <dl className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-xs text-slate-500">
                    {complaint.equipment_id ? (
                      <div className="flex gap-1">
                        <dt>Equipment:</dt>
                        <dd className="text-slate-300">
                          {equipmentById.get(complaint.equipment_id) ??
                            'Selected equipment'}
                        </dd>
                      </div>
                    ) : null}
                    {complaint.reported_error_code ? (
                      <div className="flex gap-1">
                        <dt>Error code:</dt>
                        <dd className="text-slate-300">
                          {complaint.reported_error_code}
                        </dd>
                      </div>
                    ) : null}
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
              {Math.min(offset + complaints.data.items.length, complaints.data.total)}{' '}
              of {complaints.data.total}
            </span>
            <button
              type="button"
              onClick={() => setOffset(offset + PAGE_SIZE)}
              disabled={offset + PAGE_SIZE >= complaints.data.total}
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
