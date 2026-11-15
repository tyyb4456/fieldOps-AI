import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ErrorScreen } from '../../../components/ErrorScreen'
import { FormError, Notice } from '../../../components/Feedback'
import { LoadingScreen } from '../../../components/LoadingScreen'
import { PageHeader } from '../../../components/PageHeader'
import { useApiClient } from '../../../lib/api/api-client-context'
import { formatDateTime } from '../../../lib/format'
import { useAsyncData } from '../../../lib/hooks/use-async-data'
import type { CustomerProfile } from '../../customers/types'
import type { Equipment } from '../../equipment/types'
import {
  deleteAdminEquipment,
  getAdminCustomer,
  getAdminEquipment,
  updateAdminEquipment,
} from '../api'
import { EquipmentForm } from '../components/EquipmentForm'
import { equipmentToFormValues } from '../equipment-form'
import { adminEquipmentErrorMessage } from '../errors'
import { ADMIN_ROUTES, adminCustomerPath } from '../routes'

interface EquipmentDetailData {
  equipment: Equipment
  customer: CustomerProfile
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

export function AdminEquipmentDetailPage() {
  const apiClient = useApiClient()
  const navigate = useNavigate()
  const { equipmentId = '' } = useParams()
  const [notice, setNotice] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  const { data, error, isLoading, reload } =
    useAsyncData<EquipmentDetailData>(
      async (signal) => {
        const equipment = await getAdminEquipment(
          apiClient,
          equipmentId,
          signal,
        )
        const customer = await getAdminCustomer(
          apiClient,
          equipment.customer_id,
          signal,
        )
        return { equipment, customer }
      },
      [apiClient, equipmentId],
    )

  if (isLoading) {
    return <LoadingScreen label="Loading equipment..." />
  }

  if (error || !data) {
    return (
      <ErrorScreen
        message={adminEquipmentErrorMessage(error)}
        onRetry={reload}
      />
    )
  }

  const { equipment, customer } = data

  async function saveEquipment(
    payload: Parameters<typeof updateAdminEquipment>[2],
  ) {
    setSubmitting(true)
    setActionError(null)
    try {
      await updateAdminEquipment(apiClient, equipment.id, payload)
      setEditing(false)
      setNotice('Equipment updated.')
      reload()
    } catch (caught) {
      setActionError(adminEquipmentErrorMessage(caught))
    } finally {
      setSubmitting(false)
    }
  }

  async function removeEquipment() {
    if (
      !window.confirm(
        'Delete this equipment? Historical complaints prevent deletion.',
      )
    ) {
      return
    }
    setSubmitting(true)
    setActionError(null)
    try {
      await deleteAdminEquipment(apiClient, equipment.id)
      navigate(adminCustomerPath(equipment.customer_id), {
        state: { notice: 'Equipment deleted.' },
      })
    } catch (caught) {
      setActionError(adminEquipmentErrorMessage(caught))
      setSubmitting(false)
    }
  }

  return (
    <div className="grid gap-6">
      <PageHeader
        eyebrow="Equipment"
        title={`${equipment.manufacturer} ${equipment.model}`}
        description={`${equipment.equipment_type} owned by ${customer.full_name}`}
        actions={
          <Link
            to={adminCustomerPath(equipment.customer_id)}
            className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-semibold text-slate-200 transition hover:border-slate-500 hover:text-white"
          >
            Back to customer
          </Link>
        }
      />

      {notice ? <Notice>{notice}</Notice> : null}
      <FormError message={actionError} />

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <DetailRow label="Equipment ID" value={equipment.id} />
        <DetailRow label="Customer ID" value={equipment.customer_id} />
        <DetailRow
          label="Serial number"
          value={equipment.serial_number ?? 'Not provided'}
        />
        <DetailRow
          label="Installation date"
          value={equipment.installation_date ?? 'Not provided'}
        />
        <DetailRow
          label="Registered"
          value={formatDateTime(equipment.created_at)}
        />
        <DetailRow
          label="Customer status"
          value={customer.is_active ? 'Active' : 'Inactive'}
        />
      </section>

      <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-white">
              Equipment details
            </h2>
            <p className="mt-1 text-sm text-slate-400">
              Serials and model identity affect document matching and complaints.
            </p>
          </div>
          {!editing ? (
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-medium text-slate-200 transition hover:border-slate-500"
            >
              Edit equipment
            </button>
          ) : null}
        </div>

        {editing ? (
          <div className="mt-4 rounded-xl border border-slate-800 bg-slate-950/40 p-4">
            <EquipmentForm
              mode="edit"
              initial={equipmentToFormValues(equipment)}
              submitLabel="Save changes"
              isSubmitting={submitting}
              onSubmit={saveEquipment}
              onCancel={() => setEditing(false)}
              errorMessage={adminEquipmentErrorMessage}
            />
          </div>
        ) : null}

        <div className="mt-5 border-t border-slate-800 pt-4">
          <button
            type="button"
            onClick={() => void removeEquipment()}
            disabled={submitting}
            className="rounded-xl border border-rose-500/50 px-4 py-2.5 text-sm font-medium text-rose-200 transition hover:bg-rose-500/10 disabled:cursor-not-allowed disabled:opacity-60"
          >
            Delete equipment
          </button>
          <p className="mt-2 text-xs text-slate-500">
            Equipment with historical complaints cannot be deleted. The API
            returns a conflict in that case.
          </p>
        </div>
      </section>

      <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <h2 className="text-base font-semibold text-white">
          Related workspaces
        </h2>
        <div className="mt-3 flex flex-wrap gap-2">
          <Link
            to={ADMIN_ROUTES.complaints}
            className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-medium text-slate-200 transition hover:border-slate-500"
          >
            Complaints
          </Link>
          <Link
            to={ADMIN_ROUTES.documents}
            className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-medium text-slate-200 transition hover:border-slate-500"
          >
            Technical documents
          </Link>
        </div>
      </section>

      <p className="text-xs leading-5 text-slate-500">
        Equipment changes are validated by the API, including uniqueness of
        manufacturer, model, and serial number.
      </p>
    </div>
  )
}
