import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { EmptyState } from '../../../components/EmptyState'
import { ErrorScreen } from '../../../components/ErrorScreen'
import { Notice } from '../../../components/Feedback'
import { LoadingScreen } from '../../../components/LoadingScreen'
import { PageHeader } from '../../../components/PageHeader'
import { useApiClient } from '../../../lib/api/api-client-context'
import type { PaginatedResponse } from '../../../lib/api/types'
import { formatDateTime } from '../../../lib/format'
import { useAsyncData } from '../../../lib/hooks/use-async-data'
import type { CustomerProfile } from '../../customers/types'
import type {
  Equipment,
  EquipmentCreateRequest,
} from '../../equipment/types'
import {
  createAdminCustomerEquipment,
  getAdminCustomer,
  listAdminCustomerEquipment,
} from '../api'
import { EquipmentForm } from '../components/EquipmentForm'
import { EMPTY_EQUIPMENT_FORM } from '../equipment-form'
import { adminCustomerLookupErrorMessage, adminEquipmentErrorMessage } from '../errors'
import { ADMIN_ROUTES, adminEquipmentPath } from '../routes'

const EQUIPMENT_PAGE_SIZE = 100

interface CustomerDetailData {
  customer: CustomerProfile
  equipment: PaginatedResponse<Equipment>
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-4">
      <dt className="text-xs uppercase tracking-wide text-slate-500">
        {label}
      </dt>
      <dd className="mt-1 break-words text-sm font-medium text-slate-100">
        {value}
      </dd>
    </div>
  )
}

export function AdminCustomerDetailPage() {
  const apiClient = useApiClient()
  const { customerId = '' } = useParams()
  const [notice, setNotice] = useState<string | null>(null)
  const [showEquipmentForm, setShowEquipmentForm] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  const { data, error, isLoading, reload } =
    useAsyncData<CustomerDetailData>(
      async (signal) => {
        const [customer, equipment] = await Promise.all([
          getAdminCustomer(apiClient, customerId, signal),
          listAdminCustomerEquipment(
            apiClient,
            customerId,
            { limit: EQUIPMENT_PAGE_SIZE, offset: 0 },
            signal,
          ),
        ])
        return { customer, equipment }
      },
      [apiClient, customerId],
    )

  if (isLoading) {
    return <LoadingScreen label="Loading customer..." />
  }

  if (error || !data) {
    return (
      <ErrorScreen
        message={adminCustomerLookupErrorMessage(error)}
        onRetry={reload}
      />
    )
  }

  const { customer, equipment } = data

  async function createEquipment(
    payload: Parameters<typeof createAdminCustomerEquipment>[2],
  ) {
    setSubmitting(true)
    try {
      await createAdminCustomerEquipment(apiClient, customer.id, payload)
      setShowEquipmentForm(false)
      setNotice('Equipment registered for this customer.')
      reload()
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="grid gap-6">
      <PageHeader
        eyebrow="Customer"
        title={customer.full_name}
        description={`Customer since ${formatDateTime(customer.created_at)}`}
        actions={
          <Link
            to={ADMIN_ROUTES.customers}
            className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-semibold text-slate-200 transition hover:border-slate-500 hover:text-white"
          >
            Look up another customer
          </Link>
        }
      />

      {notice ? <Notice>{notice}</Notice> : null}

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <DetailRow label="Customer ID" value={customer.id} />
        <DetailRow label="Email" value={customer.email ?? 'Not provided'} />
        <DetailRow label="Phone" value={customer.phone ?? 'Not provided'} />
        <DetailRow
          label="Preferred language"
          value={customer.preferred_language ?? 'Not provided'}
        />
        <DetailRow label="Address" value={customer.address ?? 'Not provided'} />
        <DetailRow
          label="Status"
          value={customer.is_active ? 'Active' : 'Inactive'}
        />
      </section>

      <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-white">Equipment</h2>
            <p className="mt-1 text-xs text-slate-500">
              {equipment.total} registered item
              {equipment.total === 1 ? '' : 's'} in this view
            </p>
          </div>
          <button
            type="button"
            onClick={() => setShowEquipmentForm((current) => !current)}
            className="rounded-xl bg-sky-500 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-sky-400"
          >
            {showEquipmentForm ? 'Close form' : 'Register equipment'}
          </button>
        </div>

        {showEquipmentForm ? (
          <div className="mt-4 rounded-xl border border-slate-800 bg-slate-950/40 p-4">
            <EquipmentForm
              mode="create"
              initial={EMPTY_EQUIPMENT_FORM}
              submitLabel="Register equipment"
              isSubmitting={submitting}
              onSubmit={(payload) =>
                createEquipment(payload as EquipmentCreateRequest)
              }
              onCancel={() => setShowEquipmentForm(false)}
              errorMessage={adminEquipmentErrorMessage}
            />
          </div>
        ) : null}

        {equipment.items.length === 0 ? (
          <div className="mt-4">
            <EmptyState
              title="No equipment"
              description="Register equipment so the customer can raise equipment-linked complaints."
            />
          </div>
        ) : (
          <ul className="mt-4 grid gap-3">
            {equipment.items.map((item) => (
              <li key={item.id}>
                <Link
                  to={adminEquipmentPath(item.id)}
                  className="block rounded-xl border border-slate-800 bg-slate-950/40 p-4 transition hover:border-sky-500/40"
                >
                  <h3 className="text-sm font-semibold text-white">
                    {item.manufacturer} {item.model}
                  </h3>
                  <p className="mt-1 text-xs text-slate-400">
                    {item.equipment_type}
                    {item.serial_number
                      ? ` - serial ${item.serial_number}`
                      : ''}
                  </p>
                  <p className="mt-1 font-mono text-xs text-slate-500">
                    {item.id}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <h2 className="text-base font-semibold text-white">Related records</h2>
        <p className="mt-1 text-sm text-slate-400">
          View complaints for this customer in the complaints workspace.
        </p>
        <Link
          to={ADMIN_ROUTES.complaints}
          className="mt-4 inline-flex rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-medium text-slate-200 transition hover:border-slate-500"
        >
          Open complaints workspace
        </Link>
      </section>

      <p className="text-xs leading-5 text-slate-500">
        This profile view is read-only. Customer self-service updates are
        handled in the customer workspace.
      </p>
    </div>
  )
}
