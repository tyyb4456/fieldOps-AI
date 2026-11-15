import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { EmptyState } from '../../../components/EmptyState'
import { ErrorScreen } from '../../../components/ErrorScreen'
import { FormError, Notice } from '../../../components/Feedback'
import { LoadingScreen } from '../../../components/LoadingScreen'
import { PageHeader } from '../../../components/PageHeader'
import { useApiClient } from '../../../lib/api/api-client-context'
import { apiErrorMessage } from '../../../lib/api/errors'
import type { PaginatedResponse } from '../../../lib/api/types'
import { formatDateTime, formatSymptom } from '../../../lib/format'
import { useAsyncData } from '../../../lib/hooks/use-async-data'
import {
  ComplaintStatusBadge,
  PriorityBadge,
} from '../../complaints/components/ComplaintBadges'
import type { Complaint, ComplaintHistory } from '../../complaints/types'
import type { Equipment } from '../../equipment/types'
import type {
  WorkOrder,
  WorkOrderCreateRequest,
  WorkOrderProposal,
} from '../../work-orders/types'
import {
  createWorkOrderFromComplaint,
  generateAdminProposal,
  getAdminComplaint,
  getAdminEquipment,
  listAdminComplaintHistory,
  listAdminProposals,
  listAdminWorkOrders,
  type ComplaintHistoryPage,
} from '../api'
import { ProposalStatusBadge } from '../components/AdminBadges'
import { WorkOrderForm } from '../components/WorkOrderForm'
import {
  adminProposalErrorMessage,
  adminWorkOrderErrorMessage,
} from '../errors'
import {
  ADMIN_ROUTES,
  adminProposalPath,
  adminWorkOrderPath,
} from '../routes'
import { WorkOrderStatusBadge } from '../../technicians/components/TechnicianBadges'

const HISTORY_PAGE_SIZE = 100

interface ComplaintDetailData {
  complaint: Complaint
  history: ComplaintHistoryPage
  equipment: Equipment | null
  proposals: PaginatedResponse<WorkOrderProposal>
  workOrders: PaginatedResponse<WorkOrder>
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

export function AdminComplaintDetailPage() {
  const apiClient = useApiClient()
  const { complaintId = '' } = useParams()
  const [notice, setNotice] = useState<string | null>(null)
  const [proposalError, setProposalError] = useState<string | null>(null)
  const [generating, setGenerating] = useState(false)
  const [showWorkOrderForm, setShowWorkOrderForm] = useState(false)
  const [workOrderSubmitting, setWorkOrderSubmitting] = useState(false)

  const { data, error, isLoading, reload } =
    useAsyncData<ComplaintDetailData>(
      async (signal) => {
        const complaint = await getAdminComplaint(
          apiClient,
          complaintId,
          signal,
        )
        const [history, equipment, proposals, workOrders] = await Promise.all([
          listAdminComplaintHistory(apiClient, complaintId, signal),
          complaint.equipment_id
            ? getAdminEquipment(apiClient, complaint.equipment_id, signal)
            : Promise.resolve(null),
          listAdminProposals(
            apiClient,
            { complaint_id: complaintId, limit: 20, offset: 0 },
            signal,
          ),
          listAdminWorkOrders(
            apiClient,
            { complaint_id: complaintId, limit: 20, offset: 0 },
            signal,
          ),
        ])
        return { complaint, history, equipment, proposals, workOrders }
      },
      [apiClient, complaintId],
    )

  if (isLoading) {
    return <LoadingScreen label="Loading complaint..." />
  }

  if (error || !data) {
    return (
      <ErrorScreen
        message={apiErrorMessage(error, 'Unable to load this complaint.')}
        onRetry={reload}
      />
    )
  }

  const { complaint, history, equipment, proposals, workOrders } = data
  const pendingProposal = proposals.items.find(
    (proposal) => proposal.status === 'pending_approval',
  )
  const existingWorkOrder = workOrders.items[0] ?? null
  const canConvert =
    complaint.status === 'ready_for_work_order' &&
    Boolean(complaint.equipment_id) &&
    existingWorkOrder === null

  async function generateProposal() {
    setGenerating(true)
    setProposalError(null)
    try {
      await generateAdminProposal(apiClient, complaint.id)
      setNotice(
        'Proposal generation started. The new proposal will appear when the workflow completes.',
      )
      reload()
    } catch (caught) {
      setProposalError(adminProposalErrorMessage(caught))
    } finally {
      setGenerating(false)
    }
  }

  async function createWorkOrder(
    payload: Parameters<typeof createWorkOrderFromComplaint>[2],
  ) {
    setWorkOrderSubmitting(true)
    try {
      const created = await createWorkOrderFromComplaint(
        apiClient,
        complaint.id,
        payload,
      )
      setShowWorkOrderForm(false)
      setNotice(`Work order created: ${created.title}`)
      reload()
    } finally {
      setWorkOrderSubmitting(false)
    }
  }

  return (
    <div className="grid gap-6">
      <PageHeader
        eyebrow="Complaint"
        title={`Complaint ${complaint.id.slice(0, 8)}`}
        description={`Received ${formatDateTime(complaint.created_at)} - updated ${formatDateTime(
          complaint.updated_at,
        )}`}
        actions={
          <Link
            to={ADMIN_ROUTES.complaints}
            className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-semibold text-slate-200 transition hover:border-slate-500 hover:text-white"
          >
            Back to complaints
          </Link>
        }
      />

      {notice ? <Notice>{notice}</Notice> : null}

      <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <div className="flex flex-wrap items-center gap-2">
          <ComplaintStatusBadge status={complaint.status} />
          <PriorityBadge priority={complaint.priority} />
          <span className="text-xs text-slate-500">
            {complaint.channel === 'whatsapp' ? 'WhatsApp' : 'Web'} submission
          </span>
        </div>
        <p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-slate-100">
          {complaint.description}
        </p>
        {complaint.reported_error_code ? (
          <p className="mt-3 text-sm text-amber-200">
            Reported error code: {complaint.reported_error_code}
          </p>
        ) : null}
        {complaint.reported_symptoms.length > 0 ? (
          <>
            <h2 className="mt-5 text-sm font-semibold text-slate-200">
              Reported symptoms
            </h2>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-300">
              {complaint.reported_symptoms.map((symptom, index) => (
                <li key={`${index}-${formatSymptom(symptom)}`}>
                  {formatSymptom(symptom)}
                </li>
              ))}
            </ul>
          </>
        ) : null}
      </section>

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <DetailRow label="Complaint ID" value={complaint.id} />
        <DetailRow label="Customer ID" value={complaint.customer_id} />
        <DetailRow
          label="Equipment"
          value={
            equipment
              ? `${equipment.manufacturer} ${equipment.model}`
              : complaint.equipment_id ?? 'Not linked'
          }
        />
        <DetailRow
          label="Equipment type"
          value={equipment?.equipment_type ?? 'Not available'}
        />
      </section>

      <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <h2 className="text-base font-semibold text-white">
          Work-order preparation
        </h2>
        <p className="mt-1 text-sm leading-6 text-slate-400">
          A complaint must be ready for a work order and linked to equipment.
          Generation runs asynchronously; review the proposal before approving
          it.
        </p>

        <FormError message={proposalError} />

        <div className="mt-4 grid gap-4">
          {pendingProposal ? (
            <div className="rounded-xl border border-amber-400/30 bg-amber-400/5 p-4">
              <div className="flex flex-wrap items-center gap-2">
                <ProposalStatusBadge status={pendingProposal.status} />
                <span className="text-sm text-slate-200">
                  {pendingProposal.title}
                </span>
              </div>
              <Link
                to={adminProposalPath(pendingProposal.id)}
                className="mt-3 inline-flex text-sm font-medium text-sky-300 hover:text-sky-200"
              >
                Review pending proposal
              </Link>
            </div>
          ) : canConvert ? (
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => void generateProposal()}
                disabled={generating}
                className="rounded-xl bg-sky-500 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-sky-400 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {generating ? 'Starting workflow...' : 'Generate proposal'}
              </button>
              <button
                type="button"
                onClick={() => setShowWorkOrderForm((current) => !current)}
                className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-medium text-slate-200 transition hover:border-slate-500"
              >
                {showWorkOrderForm
                  ? 'Cancel direct conversion'
                  : 'Create work order directly'}
              </button>
            </div>
          ) : null}

          {!canConvert && !pendingProposal ? (
            <p className="text-sm text-slate-500">
              {existingWorkOrder
                ? 'A work order already exists for this complaint.'
                : complaint.status !== 'ready_for_work_order'
                  ? 'This complaint is not ready for work-order conversion.'
                  : 'Link equipment to this complaint before converting it.'}
            </p>
          ) : null}

          {showWorkOrderForm && canConvert ? (
            <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-4">
              <WorkOrderForm
                mode="create"
                initial={{
                  title: complaint.description.slice(0, 80),
                  description: complaint.description,
                  priority: complaint.priority,
                }}
                submitLabel="Create work order"
                isSubmitting={workOrderSubmitting}
                onSubmit={(payload) =>
                  createWorkOrder(payload as WorkOrderCreateRequest)
                }
                onCancel={() => setShowWorkOrderForm(false)}
                errorMessage={adminWorkOrderErrorMessage}
              />
            </div>
          ) : null}
        </div>
      </section>

      <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <h2 className="text-base font-semibold text-white">Linked records</h2>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <div>
            <h3 className="text-sm font-semibold text-slate-200">
              Work orders
            </h3>
            {workOrders.items.length === 0 ? (
              <p className="mt-2 text-sm text-slate-500">
                No work order has been created.
              </p>
            ) : (
              <ul className="mt-2 grid gap-2">
                {workOrders.items.map((workOrder) => (
                  <li key={workOrder.id}>
                    <Link
                      to={adminWorkOrderPath(workOrder.id)}
                      className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-800 bg-slate-950/40 p-3 transition hover:border-sky-500/40"
                    >
                      <WorkOrderStatusBadge status={workOrder.status} />
                      <span className="text-sm text-slate-200">
                        {workOrder.title}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-200">Proposals</h3>
            {proposals.items.length === 0 ? (
              <p className="mt-2 text-sm text-slate-500">
                No proposal has been generated.
              </p>
            ) : (
              <ul className="mt-2 grid gap-2">
                {proposals.items.map((proposal) => (
                  <li key={proposal.id}>
                    <Link
                      to={adminProposalPath(proposal.id)}
                      className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-800 bg-slate-950/40 p-3 transition hover:border-sky-500/40"
                    >
                      <ProposalStatusBadge status={proposal.status} />
                      <span className="text-sm text-slate-200">
                        {proposal.title}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </section>

      <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <h2 className="text-base font-semibold text-white">History</h2>
        <p className="mt-1 text-xs text-slate-500">
          {history.total} recorded event{history.total === 1 ? '' : 's'} in this
          view
        </p>
        {history.items.length === 0 ? (
          <div className="mt-4">
            <EmptyState
              title="No history"
              description="Status and field changes will appear here."
            />
          </div>
        ) : (
          <ol className="mt-4 grid gap-2">
            {history.items.map((entry: ComplaintHistory) => (
              <li
                key={entry.id}
                className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-sm font-medium text-slate-200">
                    {entry.event_type}
                  </span>
                  <span className="text-xs text-slate-500">
                    {formatDateTime(entry.created_at)}
                  </span>
                </div>
                <p className="mt-1 text-xs text-slate-400">
                  {entry.from_status
                    ? `${entry.from_status} -> ${entry.to_status ?? entry.from_status}`
                    : `Status: ${entry.to_status ?? 'unchanged'}`}
                </p>
              </li>
            ))}
          </ol>
        )}
        {history.total > history.items.length ? (
          <p className="mt-3 text-xs text-slate-500">
            Showing {history.items.length} of {history.total} events. The API
            returns the latest {HISTORY_PAGE_SIZE} events in this view.
          </p>
        ) : null}
      </section>
    </div>
  )
}
