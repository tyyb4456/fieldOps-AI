import { Link, useNavigate } from 'react-router-dom'
import { PageHeader } from '../../../components/PageHeader'
import { useApiClient } from '../../../lib/api/api-client-context'
import { CUSTOMER_ROUTES, customerEquipmentPath } from '../../customers/routes'
import { createEquipment } from '../api'
import { EquipmentForm } from '../components/EquipmentForm'
import type { EquipmentCreateRequest } from '../types'

export function EquipmentNewPage() {
  const apiClient = useApiClient()
  const navigate = useNavigate()

  async function create(payload: EquipmentCreateRequest) {
    const equipment = await createEquipment(apiClient, payload)
    navigate(customerEquipmentPath(equipment.id), {
      state: { notice: 'Equipment registered successfully.' },
    })
  }

  return (
    <div className="grid gap-6">
      <PageHeader
        eyebrow="My equipment"
        title="Register equipment"
        description="Add the equipment installed at your site so it can be attached to future complaints."
        actions={
          <Link
            to={CUSTOMER_ROUTES.equipment}
            className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-semibold text-slate-200 transition hover:border-slate-500 hover:text-white"
          >
            Back to equipment
          </Link>
        }
      />

      <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <EquipmentForm submitLabel="Register equipment" onSubmit={create} />
      </section>
    </div>
  )
}
