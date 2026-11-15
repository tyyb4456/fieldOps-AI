import { Link, useNavigate } from 'react-router-dom'
import { PageHeader } from '../../../components/PageHeader'
import { useApiClient } from '../../../lib/api/api-client-context'
import { useAsyncData } from '../../../lib/hooks/use-async-data'
import {
  CUSTOMER_ROUTES,
  customerComplaintPath,
} from '../../customers/routes'
import { listEquipment } from '../../equipment/api'
import { createComplaint } from '../api'
import { ComplaintForm } from '../components/ComplaintForm'
import type { ComplaintCreateRequest } from '../types'

export function ComplaintNewPage() {
  const apiClient = useApiClient()
  const navigate = useNavigate()
  const equipment = useAsyncData(
    (signal) => listEquipment(apiClient, { limit: 100 }, signal),
    [apiClient],
  )

  async function submit(payload: ComplaintCreateRequest) {
    const complaint = await createComplaint(apiClient, payload)
    navigate(customerComplaintPath(complaint.id), {
      state: { notice: 'Your complaint has been submitted.' },
    })
  }

  return (
    <div className="grid gap-6">
      <PageHeader
        eyebrow="My complaints"
        title="Report a problem"
        description="Describe what is happening with your equipment. You can choose a registered equipment record or submit without one."
        actions={
          <Link
            to={CUSTOMER_ROUTES.complaints}
            className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-semibold text-slate-200 transition hover:border-slate-500 hover:text-white"
          >
            Back to complaints
          </Link>
        }
      />

      <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <ComplaintForm
          equipment={equipment.data?.items ?? []}
          isEquipmentLoading={equipment.isLoading}
          equipmentLoadError={Boolean(equipment.error)}
          onRetryEquipment={equipment.reload}
          onSubmit={submit}
        />
      </section>
    </div>
  )
}
