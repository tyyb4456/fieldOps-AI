import { useState, type FormEvent } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { EmptyState } from '../../../components/EmptyState'
import { ErrorScreen } from '../../../components/ErrorScreen'
import { Notice } from '../../../components/Feedback'
import { inputClassName } from '../../../components/FormField'
import { LoadingScreen } from '../../../components/LoadingScreen'
import { PageHeader } from '../../../components/PageHeader'
import { useApiClient } from '../../../lib/api/api-client-context'
import { apiErrorMessage } from '../../../lib/api/errors'
import { formatDate } from '../../../lib/format'
import { useAsyncData } from '../../../lib/hooks/use-async-data'
import { CUSTOMER_ROUTES, customerEquipmentPath } from '../../customers/routes'
import { listEquipment } from '../api'

const PAGE_SIZE = 12

export function EquipmentListPage() {
  const apiClient = useApiClient()
  const location = useLocation()
  const [typeInput, setTypeInput] = useState('')
  const [equipmentType, setEquipmentType] = useState('')
  const [offset, setOffset] = useState(0)
  const notice = (location.state as { notice?: string } | null)?.notice

  const { data, error, isLoading, reload } = useAsyncData(
    (signal) =>
      listEquipment(
        apiClient,
        {
          equipment_type: equipmentType || undefined,
          limit: PAGE_SIZE,
          offset,
        },
        signal,
      ),
    [apiClient, equipmentType, offset],
  )

  function applyFilter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setOffset(0)
    setEquipmentType(typeInput.trim())
  }

  function clearFilter() {
    setTypeInput('')
    setEquipmentType('')
    setOffset(0)
  }

  const page = Math.floor(offset / PAGE_SIZE) + 1
  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1

  return (
    <div className="grid gap-6">
      <PageHeader
        eyebrow="My equipment"
        title="Registered equipment"
        description="These are the equipment records that belong to your customer account."
        actions={
          <Link
            to={CUSTOMER_ROUTES.newEquipment}
            className="rounded-xl bg-sky-500 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-sky-400"
          >
            Register equipment
          </Link>
        }
      />

      {notice ? <Notice>{notice}</Notice> : null}

      <form
        onSubmit={applyFilter}
        className="flex flex-col gap-3 rounded-2xl border border-slate-800 bg-slate-900/60 p-4 sm:flex-row sm:items-end"
      >
        <div className="grid flex-1 gap-1.5">
          <label
            htmlFor="equipment-type-filter"
            className="text-sm font-medium text-slate-200"
          >
            Filter by equipment type
          </label>
          <input
            id="equipment-type-filter"
            className={inputClassName}
            value={typeInput}
            placeholder="For example solar_inverter"
            maxLength={80}
            onChange={(event) => setTypeInput(event.target.value)}
          />
        </div>
        <div className="flex gap-2">
          <button
            type="submit"
            className="rounded-xl bg-slate-700 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-600"
          >
            Apply filter
          </button>
          {equipmentType ? (
            <button
              type="button"
              onClick={clearFilter}
              className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-medium text-slate-200 transition hover:border-slate-500"
            >
              Clear
            </button>
          ) : null}
        </div>
      </form>

      {isLoading ? (
        <LoadingScreen label="Loading equipment..." />
      ) : error ? (
        <ErrorScreen
          message={apiErrorMessage(error, 'Unable to load your equipment.')}
          onRetry={reload}
        />
      ) : !data ? null : data.items.length === 0 ? (
        <EmptyState
          title={
            equipmentType
              ? 'No equipment matches this filter'
              : 'No equipment registered'
          }
          description={
            equipmentType
              ? 'Try a different equipment type or clear the filter.'
              : 'Register the equipment you want to attach to future complaints.'
          }
          action={
            equipmentType ? (
              <button
                type="button"
                onClick={clearFilter}
                className="rounded-lg border border-slate-700 px-4 py-2 text-sm font-medium text-slate-200 transition hover:border-slate-500"
              >
                Clear filter
              </button>
            ) : (
              <Link
                to={CUSTOMER_ROUTES.newEquipment}
                className="inline-flex rounded-lg bg-sky-500 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-sky-400"
              >
                Register equipment
              </Link>
            )
          }
        />
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
            <span>
              {data.total} equipment record{data.total === 1 ? '' : 's'}
              {equipmentType ? ` of type ${equipmentType}` : ''}
            </span>
            <span>
              Page {page} of {totalPages}
            </span>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {data.items.map((item) => (
              <Link
                key={item.id}
                to={customerEquipmentPath(item.id)}
                className="flex h-full flex-col rounded-2xl border border-slate-800 bg-slate-900/60 p-5 transition hover:border-sky-500/40"
              >
                <p className="text-xs font-medium uppercase tracking-wide text-sky-400">
                  {item.equipment_type}
                </p>
                <h2 className="mt-2 text-base font-semibold text-white">
                  {item.manufacturer} {item.model}
                </h2>
                <dl className="mt-4 grid gap-2 text-xs text-slate-400">
                  <div>
                    <dt className="text-slate-500">Serial number</dt>
                    <dd className="mt-0.5 break-words text-slate-300">
                      {item.serial_number ?? 'Not provided'}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-slate-500">Installed</dt>
                    <dd className="mt-0.5 text-slate-300">
                      {formatDate(item.installation_date)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-slate-500">Registered</dt>
                    <dd className="mt-0.5 text-slate-300">
                      {formatDate(item.created_at)}
                    </dd>
                  </div>
                </dl>
                <span className="mt-4 text-sm font-medium text-sky-300">
                  View details
                </span>
              </Link>
            ))}
          </div>

          <div className="flex items-center justify-between gap-3">
            <button
              type="button"
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              disabled={offset === 0}
              className="rounded-lg border border-slate-700 px-4 py-2 text-sm font-medium text-slate-200 transition hover:border-slate-500 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Previous
            </button>
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
    </div>
  )
}
