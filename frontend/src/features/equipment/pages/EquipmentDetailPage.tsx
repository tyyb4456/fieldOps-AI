import { useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { ErrorScreen } from '../../../components/ErrorScreen'
import { FormError, Notice } from '../../../components/Feedback'
import { LoadingScreen } from '../../../components/LoadingScreen'
import { PageHeader } from '../../../components/PageHeader'
import { useApiClient } from '../../../lib/api/api-client-context'
import { ApiError, apiErrorMessage } from '../../../lib/api/errors'
import { formatDate, formatDateTime } from '../../../lib/format'
import { useAsyncData } from '../../../lib/hooks/use-async-data'
import {
  CUSTOMER_ROUTES,
  customerEquipmentEditPath,
} from '../../customers/routes'
import { deleteEquipment, getEquipment } from '../api'

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

function deleteErrorMessage(error: unknown): string {
  if (
    error instanceof ApiError &&
    error.status === 409 &&
    error.code === 'equipment_in_use'
  ) {
    return 'This equipment is referenced by an existing complaint and cannot be deleted. You can update its details instead.'
  }

  return apiErrorMessage(error, 'Unable to delete this equipment.')
}

export function EquipmentDetailPage() {
  const apiClient = useApiClient()
  const navigate = useNavigate()
  const location = useLocation()
  const { equipmentId = '' } = useParams()
  const notice = (location.state as { notice?: string } | null)?.notice
  const [isDeleting, setIsDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const { data, error, isLoading, reload } = useAsyncData(
    (signal) => getEquipment(apiClient, equipmentId, signal),
    [apiClient, equipmentId],
  )

  if (isLoading) {
    return <LoadingScreen label="Loading equipment details..." />
  }

  if (error || !data) {
    return (
      <ErrorScreen
        message={apiErrorMessage(
          error,
          'Unable to load this equipment record.',
        )}
        onRetry={reload}
      />
    )
  }

  const equipment = data

  async function handleDelete() {
    if (
      !window.confirm(
        `Delete ${equipment.manufacturer} ${equipment.model}? This cannot be undone.`,
      )
    ) {
      return
    }

    setIsDeleting(true)
    setDeleteError(null)

    try {
      await deleteEquipment(apiClient, equipment.id)
      navigate(CUSTOMER_ROUTES.equipment, {
        state: { notice: `${equipment.manufacturer} ${equipment.model} was deleted.` },
      })
    } catch (err) {
      setDeleteError(deleteErrorMessage(err))
      setIsDeleting(false)
    }
  }

  return (
    <div className="grid gap-6">
      <PageHeader
        eyebrow="Equipment"
        title={`${data.manufacturer} ${data.model}`}
        description={data.equipment_type}
        actions={
          <>
            <Link
              to={customerEquipmentEditPath(data.id)}
              className="rounded-xl bg-sky-500 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-sky-400"
            >
              Edit equipment
            </Link>
            <Link
              to={CUSTOMER_ROUTES.equipment}
              className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-semibold text-slate-200 transition hover:border-slate-500 hover:text-white"
            >
              Back to equipment
            </Link>
          </>
        }
      />

      {notice ? <Notice>{notice}</Notice> : null}

      <section className="grid gap-4 sm:grid-cols-2">
        <DetailRow label="Manufacturer" value={data.manufacturer} />
        <DetailRow label="Model" value={data.model} />
        <DetailRow label="Equipment type" value={data.equipment_type} />
        <DetailRow
          label="Serial number"
          value={data.serial_number ?? 'Not provided'}
        />
        <DetailRow
          label="Installation date"
          value={formatDate(data.installation_date)}
        />
        <DetailRow label="Registered" value={formatDateTime(data.created_at)} />
        <DetailRow label="Equipment ID" value={data.id} />
      </section>

      <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <h2 className="text-base font-semibold text-white">Delete equipment</h2>
        <p className="mt-1 text-sm text-slate-400">
          Equipment linked to a complaint cannot be deleted. Update the record
          instead if it is still in use.
        </p>
        {deleteError ? (
          <div className="mt-4">
            <FormError message={deleteError} />
          </div>
        ) : null}
        <button
          type="button"
          onClick={handleDelete}
          disabled={isDeleting}
          className="mt-4 rounded-xl border border-rose-500/40 px-4 py-2.5 text-sm font-semibold text-rose-300 transition hover:border-rose-400 hover:bg-rose-500/10 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isDeleting ? 'Deleting...' : 'Delete equipment'}
        </button>
      </section>
    </div>
  )
}
