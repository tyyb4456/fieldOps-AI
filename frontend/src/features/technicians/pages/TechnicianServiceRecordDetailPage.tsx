import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ErrorScreen } from '../../../components/ErrorScreen'
import { InlineWarning, Notice } from '../../../components/Feedback'
import { LoadingScreen } from '../../../components/LoadingScreen'
import { PageHeader } from '../../../components/PageHeader'
import { useApiClient } from '../../../lib/api/api-client-context'
import { formatDateTime, formatSymptom } from '../../../lib/format'
import { useAsyncData } from '../../../lib/hooks/use-async-data'
import {
  getServiceRecord,
  getWorkOrder,
  updateServiceRecord,
} from '../../work-orders/api'
import type { ServiceRecord, WorkOrder } from '../../work-orders/types'
import { ServiceRecordForm } from '../components/ServiceRecordForm'
import { WorkOrderStatusBadge } from '../components/TechnicianBadges'
import { serviceRecordErrorMessage } from '../errors'
import { canModifyServiceRecords } from '../lifecycle'
import { technicianWorkOrderPath } from '../routes'

interface ServiceRecordDetailData {
  record: ServiceRecord
  workOrder: WorkOrder
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

export function TechnicianServiceRecordDetailPage() {
  const apiClient = useApiClient()
  const { serviceRecordId = '' } = useParams()
  const [isEditing, setIsEditing] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  const { data, error, isLoading, reload, setData } =
    useAsyncData<ServiceRecordDetailData>(async (signal) => {
      const record = await getServiceRecord(apiClient, serviceRecordId, signal)
      const workOrder = await getWorkOrder(
        apiClient,
        record.work_order_id,
        signal,
      )
      return { record, workOrder }
    }, [apiClient, serviceRecordId])

  if (isLoading) {
    return <LoadingScreen label="Loading service record..." />
  }

  if (error || !data) {
    return (
      <ErrorScreen
        message={serviceRecordErrorMessage(error)}
        onRetry={reload}
      />
    )
  }

  const { record, workOrder } = data
  const canEdit = canModifyServiceRecords(workOrder.status)

  async function save(
    payload: Parameters<typeof updateServiceRecord>[2],
  ) {
    setIsSubmitting(true)
    try {
      const updated = await updateServiceRecord(
        apiClient,
        record.id,
        payload,
      )
      setData({ record: updated, workOrder })
      setIsEditing(false)
      setNotice('Service record updated.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="grid gap-6">
      <PageHeader
        eyebrow="Service record"
        title="Service activity"
        description={`Recorded ${formatDateTime(record.recorded_at)}`}
        actions={
          <Link
            to={technicianWorkOrderPath(record.work_order_id)}
            className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-semibold text-slate-200 transition hover:border-slate-500 hover:text-white"
          >
            Back to work order
          </Link>
        }
      />

      {notice ? <Notice>{notice}</Notice> : null}

      <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <div className="flex flex-wrap items-center gap-2">
          <WorkOrderStatusBadge status={workOrder.status} />
          <span className="text-xs text-slate-500">
            {record.parts_used.length} part
            {record.parts_used.length === 1 ? '' : 's'} used
          </span>
        </div>

        {isEditing ? (
          <div className="mt-4 rounded-xl border border-slate-800 bg-slate-950/40 p-4">
            <ServiceRecordForm
              initial={{
                findings: record.findings ?? '',
                workPerformed: record.work_performed ?? '',
                partsUsed: record.parts_used
                  .map((part) => formatSymptom(part))
                  .join('\n'),
              }}
              submitLabel="Save changes"
              isSubmitting={isSubmitting}
              onSubmit={save}
              onCancel={() => setIsEditing(false)}
              errorMessage={serviceRecordErrorMessage}
            />
          </div>
        ) : (
          <>
            <h2 className="mt-4 text-sm font-semibold text-slate-200">
              Findings
            </h2>
            <p className="mt-2 whitespace-pre-wrap text-sm leading-7 text-slate-100">
              {record.findings ?? 'No findings were recorded.'}
            </p>

            <h2 className="mt-5 text-sm font-semibold text-slate-200">
              Work performed
            </h2>
            <p className="mt-2 whitespace-pre-wrap text-sm leading-7 text-slate-100">
              {record.work_performed ?? 'No work performed was recorded.'}
            </p>

            <h2 className="mt-5 text-sm font-semibold text-slate-200">
              Parts used
            </h2>
            {record.parts_used.length === 0 ? (
              <p className="mt-2 text-sm text-slate-400">
                No parts were recorded.
              </p>
            ) : (
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-300">
                {record.parts_used.map((part, index) => (
                  <li key={`${index}-${formatSymptom(part)}`}>
                    {formatSymptom(part)}
                  </li>
                ))}
              </ul>
            )}
          </>
        )}

        {!isEditing ? (
          <div className="mt-5">
            {canEdit ? (
              <button
                type="button"
                onClick={() => setIsEditing(true)}
                className="rounded-xl bg-sky-500 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-sky-400"
              >
                Edit service record
              </button>
            ) : (
              <InlineWarning>
                This service record is read-only because the work order is no
                longer in an editable state.
              </InlineWarning>
            )}
          </div>
        ) : null}
      </section>

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <DetailRow label="Service record ID" value={record.id} />
        <DetailRow label="Work order ID" value={record.work_order_id} />
        <DetailRow label="Equipment ID" value={record.equipment_id} />
        <DetailRow label="Technician ID" value={record.technician_id} />
        <DetailRow label="Recorded" value={formatDateTime(record.recorded_at)} />
        <DetailRow
          label="Work-order status"
          value={workOrder.status.replaceAll('_', ' ')}
        />
      </section>
    </div>
  )
}
