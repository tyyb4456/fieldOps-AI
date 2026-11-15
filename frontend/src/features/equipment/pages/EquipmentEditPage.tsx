import { Link, useNavigate, useParams } from 'react-router-dom'
import { ErrorScreen } from '../../../components/ErrorScreen'
import { LoadingScreen } from '../../../components/LoadingScreen'
import { PageHeader } from '../../../components/PageHeader'
import { useApiClient } from '../../../lib/api/api-client-context'
import { apiErrorMessage } from '../../../lib/api/errors'
import { useAsyncData } from '../../../lib/hooks/use-async-data'
import { customerEquipmentPath } from '../../customers/routes'
import { getEquipment, updateEquipment } from '../api'
import { EquipmentForm } from '../components/EquipmentForm'
import type { EquipmentCreateRequest } from '../types'

export function EquipmentEditPage() {
  const apiClient = useApiClient()
  const navigate = useNavigate()
  const { equipmentId = '' } = useParams()
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

  async function save(payload: EquipmentCreateRequest) {
    const updated = await updateEquipment(apiClient, equipment.id, payload)
    navigate(customerEquipmentPath(updated.id), {
      state: { notice: 'Equipment updated successfully.' },
    })
  }

  return (
    <div className="grid gap-6">
      <PageHeader
        eyebrow="My equipment"
        title={`Edit ${data.manufacturer} ${data.model}`}
        description="Update the equipment details stored on your customer account."
        actions={
          <Link
            to={customerEquipmentPath(data.id)}
            className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-semibold text-slate-200 transition hover:border-slate-500 hover:text-white"
          >
            Cancel
          </Link>
        }
      />

      <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <EquipmentForm
          equipment={data}
          submitLabel="Save changes"
          onSubmit={save}
        />
      </section>
    </div>
  )
}
