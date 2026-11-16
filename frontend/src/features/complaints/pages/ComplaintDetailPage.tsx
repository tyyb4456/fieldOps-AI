import { Link, useLocation, useParams } from 'react-router-dom'
import { ErrorScreen } from '../../../components/ErrorScreen'
import { Notice } from '../../../components/Feedback'
import { LoadingScreen } from '../../../components/LoadingScreen'
import { PageHeader } from '../../../components/PageHeader'
import { useApiClient } from '../../../lib/api/api-client-context'
import { formatDateTime, formatSymptom } from '../../../lib/format'
import { useAsyncData } from '../../../lib/hooks/use-async-data'
import { CUSTOMER_ROUTES, customerEquipmentPath } from '../../customers/routes'
import { getEquipment } from '../../equipment/api'
import { ComplaintConversations } from '../../conversations/components/ComplaintConversations'
import { getComplaint } from '../api'
import { complaintDetailErrorMessage } from '../errors'
import {
  ComplaintStatusBadge,
  PriorityBadge,
} from '../components/ComplaintBadges'
import {
  CHANNEL_LABELS,
  complaintStatusLabel,
  priorityLabel,
} from '../labels'

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

function LinkedEquipment({ equipmentId }: { equipmentId: string }) {
  const apiClient = useApiClient()
  const { data, error, isLoading } = useAsyncData(
    (signal) => getEquipment(apiClient, equipmentId, signal),
    [apiClient, equipmentId],
  )

  if (isLoading) {
    return <p className="text-sm text-slate-400">Loading equipment...</p>
  }

  if (error || !data) {
    return (
      <p className="text-sm text-slate-400">
        The linked equipment record is no longer available.{' '}
        <Link
          to={CUSTOMER_ROUTES.equipment}
          className="font-medium text-sky-300 hover:text-sky-200"
        >
          View my equipment
        </Link>
      </p>
    )
  }

  return (
    <Link
      to={customerEquipmentPath(data.id)}
      className="block rounded-xl border border-slate-800 bg-slate-950/40 p-4 transition hover:border-sky-500/40"
    >
      <p className="text-sm font-semibold text-white">
        {data.manufacturer} {data.model}
      </p>
      <p className="mt-1 text-xs text-slate-400">
        {data.equipment_type}
        {data.serial_number ? ` - Serial ${data.serial_number}` : ''}
      </p>
    </Link>
  )
}

export function ComplaintDetailPage() {
  const apiClient = useApiClient()
  const location = useLocation()
  const { complaintId = '' } = useParams()
  const notice = (location.state as { notice?: string } | null)?.notice
  const { data, error, isLoading, reload } = useAsyncData(
    (signal) => getComplaint(apiClient, complaintId, signal),
    [apiClient, complaintId],
  )

  if (isLoading) {
    return <LoadingScreen label="Loading complaint details..." />
  }

  if (error || !data) {
    return (
      <ErrorScreen
        message={complaintDetailErrorMessage(error)}
        onRetry={reload}
      />
    )
  }

  return (
    <div className="grid gap-6">
      <PageHeader
        eyebrow="Complaint"
        title="Complaint details"
        description={`Submitted ${formatDateTime(data.created_at)}`}
        actions={
          <Link
            to={CUSTOMER_ROUTES.complaints}
            className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-semibold text-slate-200 transition hover:border-slate-500 hover:text-white"
          >
            Back to complaints
          </Link>
        }
      />

      {notice ? <Notice>{notice}</Notice> : null}

      <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <div className="flex flex-wrap items-center gap-2">
          <ComplaintStatusBadge status={data.status} />
          <PriorityBadge priority={data.priority} />
          <span className="text-xs text-slate-500">
            {CHANNEL_LABELS[data.channel]}
          </span>
        </div>
        <h2 className="mt-4 text-sm font-semibold text-slate-200">
          Reported problem
        </h2>
        <p className="mt-2 whitespace-pre-wrap text-sm leading-7 text-slate-100">
          {data.description}
        </p>

        {data.reported_symptoms.length > 0 ? (
          <>
            <h2 className="mt-5 text-sm font-semibold text-slate-200">
              Reported symptoms
            </h2>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-300">
              {data.reported_symptoms.map((symptom, index) => (
                <li key={`${index}-${formatSymptom(symptom)}`}>
                  {formatSymptom(symptom)}
                </li>
              ))}
            </ul>
          </>
        ) : null}
      </section>

      <section className="grid gap-4 sm:grid-cols-2">
        <DetailRow label="Status" value={complaintStatusLabel(data.status)} />
        <DetailRow label="Priority" value={priorityLabel(data.priority)} />
        <DetailRow
          label="Error code"
          value={data.reported_error_code ?? 'Not provided'}
        />
        <DetailRow label="Submitted" value={formatDateTime(data.created_at)} />
        <DetailRow label="Last updated" value={formatDateTime(data.updated_at)} />
        <DetailRow label="Complaint ID" value={data.id} />
      </section>

      <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <h2 className="text-base font-semibold text-white">Linked equipment</h2>
        <div className="mt-3">
          {data.equipment_id ? (
            <LinkedEquipment equipmentId={data.equipment_id} />
          ) : (
            <p className="text-sm text-slate-400">
              No equipment was attached to this complaint.
            </p>
          )}
        </div>
      </section>

      <ComplaintConversations complaintId={data.id} />

      <p className="text-xs leading-5 text-slate-500">
        Status updates are managed by the service team. This page does not run
        diagnostics or create work orders automatically.
      </p>
    </div>
  )
}
