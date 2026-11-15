import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { EmptyState } from '../../../components/EmptyState'
import { ErrorScreen } from '../../../components/ErrorScreen'
import { FormError, InlineWarning, Notice } from '../../../components/Feedback'
import { LoadingScreen } from '../../../components/LoadingScreen'
import { PageHeader } from '../../../components/PageHeader'
import { useApiClient } from '../../../lib/api/api-client-context'
import type {
  PaginatedResponse,
  WorkOrderStatus,
} from '../../../lib/api/types'
import { formatDateTime, formatSymptom } from '../../../lib/format'
import { useAsyncData } from '../../../lib/hooks/use-async-data'
import type {
  Assignment,
  TechnicianSummary,
} from '../../assignments/types'
import { PriorityBadge } from '../../complaints/components/ComplaintBadges'
import {
  AssignmentStatusBadge,
  EvidenceStatusBadge,
  WorkOrderStatusBadge,
} from '../../technicians/components/TechnicianBadges'
import type {
  CompletionReport,
  ServiceRecord,
  WorkOrder,
  WorkOrderUpdateRequest,
} from '../../work-orders/types'
import {
  createAdminAssignment,
  getAdminWorkOrder,
  listAdminAssignments,
  listAdminServiceRecords,
  listAdminTechnicians,
  listAdminWorkOrderCompletionReports,
  reassignAdminAssignment,
  updateAdminWorkOrder,
  updateAdminWorkOrderStatus,
  withdrawAdminAssignment,
} from '../api'
import { AssignmentOfferForm } from '../components/AssignmentOfferForm'
import { WorkOrderForm } from '../components/WorkOrderForm'
import { AdminWorkOrderStatusActions } from '../components/WorkOrderStatusActions'
import {
  adminAssignmentErrorMessage,
  adminWorkOrderErrorMessage,
} from '../errors'
import {
  ADMIN_ROUTES,
  adminCompletionReportPath,
  adminComplaintPath,
  adminEquipmentPath,
} from '../routes'

const DETAIL_PAGE_SIZE = 100
const EDITABLE_STATUSES: readonly WorkOrderStatus[] = [
  'draft',
  'validated',
  'awaiting_assignment',
]
const ASSIGNABLE_STATUSES: readonly WorkOrderStatus[] = [
  'validated',
  'awaiting_assignment',
  'assigned',
  'accepted',
]
const WITHDRAWABLE_STATUSES: readonly WorkOrderStatus[] = [
  'awaiting_assignment',
  'assigned',
  'accepted',
]

interface WorkOrderDetailData {
  workOrder: WorkOrder
  assignments: PaginatedResponse<Assignment>
  completionReports: PaginatedResponse<CompletionReport>
  serviceRecords: PaginatedResponse<ServiceRecord>
  technicians: PaginatedResponse<TechnicianSummary>
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

export function AdminWorkOrderDetailPage() {
  const apiClient = useApiClient()
  const { workOrderId = '' } = useParams()
  const [notice, setNotice] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)
  const [editSubmitting, setEditSubmitting] = useState(false)
  const [statusSubmitting, setStatusSubmitting] = useState(false)
  const [statusError, setStatusError] = useState<string | null>(null)
  const [assignmentSubmitting, setAssignmentSubmitting] = useState(false)
  const [assignmentError, setAssignmentError] = useState<string | null>(null)
  const [withdrawingId, setWithdrawingId] = useState<string | null>(null)

  const { data, error, isLoading, reload } =
    useAsyncData<WorkOrderDetailData>(
      async (signal) => {
        const workOrder = await getAdminWorkOrder(
          apiClient,
          workOrderId,
          signal,
        )
        const [
          assignments,
          completionReports,
          serviceRecords,
          technicians,
        ] = await Promise.all([
          listAdminAssignments(
            apiClient,
            { work_order_id: workOrderId, limit: DETAIL_PAGE_SIZE },
            signal,
          ),
          listAdminWorkOrderCompletionReports(
            apiClient,
            workOrderId,
            { limit: DETAIL_PAGE_SIZE },
            signal,
          ),
          listAdminServiceRecords(
            apiClient,
            { work_order_id: workOrderId, limit: DETAIL_PAGE_SIZE },
            signal,
          ),
          listAdminTechnicians(
            apiClient,
            { limit: DETAIL_PAGE_SIZE, offset: 0 },
            signal,
          ),
        ])
        return {
          workOrder,
          assignments,
          completionReports,
          serviceRecords,
          technicians,
        }
      },
      [apiClient, workOrderId],
    )

  if (isLoading) {
    return <LoadingScreen label="Loading work order..." />
  }

  if (error || !data) {
    return (
      <ErrorScreen
        message={adminWorkOrderErrorMessage(error)}
        onRetry={reload}
      />
    )
  }

  const {
    workOrder,
    assignments,
    completionReports,
    serviceRecords,
    technicians,
  } = data
  const activeAssignment = assignments.items.find(
    (assignment) =>
      assignment.assignment_status === 'offered' ||
      assignment.assignment_status === 'accepted',
  )
  const isEditable = EDITABLE_STATUSES.includes(workOrder.status)
  const canAssign = ASSIGNABLE_STATUSES.includes(workOrder.status)
  const canWithdraw = WITHDRAWABLE_STATUSES.includes(workOrder.status)

  async function saveWorkOrder(
    payload: Parameters<typeof updateAdminWorkOrder>[2],
  ) {
    setEditSubmitting(true)
    try {
      await updateAdminWorkOrder(apiClient, workOrder.id, payload)
      setEditing(false)
      setNotice('Work-order details updated.')
      reload()
    } finally {
      setEditSubmitting(false)
    }
  }

  async function transitionStatus(target: WorkOrderStatus) {
    setStatusSubmitting(true)
    setStatusError(null)
    try {
      await updateAdminWorkOrderStatus(apiClient, workOrder.id, target)
      setNotice(
        `Work order moved to ${target.replaceAll('_', ' ')}.`,
      )
      reload()
    } catch (caught) {
      setStatusError(adminWorkOrderErrorMessage(caught))
    } finally {
      setStatusSubmitting(false)
    }
  }

  async function offerAssignment(technicianId: string) {
    setAssignmentSubmitting(true)
    setAssignmentError(null)
    try {
      if (activeAssignment) {
        await reassignAdminAssignment(
          apiClient,
          workOrder.id,
          technicianId,
        )
        setNotice('Work order reassigned to the selected technician.')
      } else {
        await createAdminAssignment(apiClient, workOrder.id, technicianId)
        setNotice('Assignment offered to the selected technician.')
      }
      reload()
    } catch (caught) {
      setAssignmentError(adminAssignmentErrorMessage(caught))
    } finally {
      setAssignmentSubmitting(false)
    }
  }

  async function withdrawAssignment(assignmentId: string) {
    if (
      !window.confirm(
        'Withdraw this assignment? The technician will no longer be able to accept it.',
      )
    ) {
      return
    }
    setWithdrawingId(assignmentId)
    setAssignmentError(null)
    try {
      await withdrawAdminAssignment(apiClient, assignmentId)
      setNotice('Assignment withdrawn.')
      reload()
    } catch (caught) {
      setAssignmentError(adminAssignmentErrorMessage(caught))
    } finally {
      setWithdrawingId(null)
    }
  }

  return (
    <div className="grid gap-6">
      <PageHeader
        eyebrow="Work order"
        title={workOrder.title}
        description={`Created ${formatDateTime(workOrder.created_at)} - updated ${formatDateTime(
          workOrder.updated_at,
        )}`}
        actions={
          <Link
            to={ADMIN_ROUTES.workOrders}
            className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-semibold text-slate-200 transition hover:border-slate-500 hover:text-white"
          >
            Back to work orders
          </Link>
        }
      />

      {notice ? <Notice>{notice}</Notice> : null}

      <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <div className="flex flex-wrap items-center gap-2">
          <WorkOrderStatusBadge status={workOrder.status} />
          <PriorityBadge priority={workOrder.priority} />
          <span className="text-xs text-slate-500">
            {serviceRecords.total} service record
            {serviceRecords.total === 1 ? '' : 's'}
          </span>
        </div>

        <p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-slate-100">
          {workOrder.description}
        </p>

        {workOrder.diagnostic_checklist.length > 0 ? (
          <>
            <h2 className="mt-5 text-sm font-semibold text-slate-200">
              Diagnostic checklist
            </h2>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-300">
              {workOrder.diagnostic_checklist.map((item, index) => (
                <li key={`${index}-${formatSymptom(item)}`}>
                  {formatSymptom(item)}
                </li>
              ))}
            </ul>
          </>
        ) : null}

        <div className="mt-4 flex flex-wrap gap-3 text-sm">
          <Link
            to={adminComplaintPath(workOrder.complaint_id)}
            className="font-medium text-sky-300 hover:text-sky-200"
          >
            View complaint
          </Link>
          <Link
            to={adminEquipmentPath(workOrder.equipment_id)}
            className="font-medium text-sky-300 hover:text-sky-200"
          >
            View equipment
          </Link>
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <DetailRow label="Work order ID" value={workOrder.id} />
        <DetailRow label="Complaint ID" value={workOrder.complaint_id} />
        <DetailRow label="Equipment ID" value={workOrder.equipment_id} />
        <DetailRow
          label="Active assignment"
          value={
            activeAssignment
              ? `${activeAssignment.assignment_status} - ${activeAssignment.id}`
              : 'None'
          }
        />
      </section>

      {isEditable ? (
        <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold text-white">
                Editable fields
              </h2>
              <p className="mt-1 text-sm text-slate-400">
                Title, description, and priority can be changed while the work
                order is draft, validated, or awaiting assignment.
              </p>
            </div>
            {!editing ? (
              <button
                type="button"
                onClick={() => setEditing(true)}
                className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-medium text-slate-200 transition hover:border-slate-500"
              >
                Edit details
              </button>
            ) : null}
          </div>
          {editing ? (
            <div className="mt-4 rounded-xl border border-slate-800 bg-slate-950/40 p-4">
              <WorkOrderForm
                mode="edit"
                initial={{
                  title: workOrder.title,
                  description: workOrder.description,
                  priority: workOrder.priority,
                }}
                submitLabel="Save changes"
                isSubmitting={editSubmitting}
                onSubmit={(payload) =>
                  saveWorkOrder(payload as WorkOrderUpdateRequest)
                }
                onCancel={() => setEditing(false)}
                errorMessage={adminWorkOrderErrorMessage}
              />
            </div>
          ) : null}
        </section>
      ) : null}

      <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <h2 className="text-base font-semibold text-white">Status actions</h2>
        <p className="mt-1 text-sm text-slate-400">
          Transitions are validated by the API. Completion is terminal.
        </p>
        <div className="mt-4">
          <AdminWorkOrderStatusActions
            status={workOrder.status}
            isSubmitting={statusSubmitting}
            onTransition={transitionStatus}
            error={statusError}
          />
        </div>
      </section>

      <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <h2 className="text-base font-semibold text-white">Assignment</h2>
        <p className="mt-1 text-sm text-slate-400">
          Offer or reassign the work order to an available technician.
        </p>
        <div className="mt-4 grid gap-4">
          <FormError message={assignmentError} />
          {activeAssignment ? (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-950/40 p-4">
              <div className="flex flex-wrap items-center gap-2">
                <AssignmentStatusBadge
                  status={activeAssignment.assignment_status}
                />
                <span className="text-sm text-slate-300">
                  Technician {activeAssignment.technician_id}
                </span>
                <span className="text-xs text-slate-500">
                  Offered {formatDateTime(activeAssignment.assigned_at)}
                </span>
              </div>
              {canWithdraw ? (
                <button
                  type="button"
                  onClick={() => void withdrawAssignment(activeAssignment.id)}
                  disabled={withdrawingId !== null}
                  className="rounded-lg border border-rose-500/40 px-3 py-2 text-xs font-medium text-rose-200 transition hover:bg-rose-500/10 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {withdrawingId === activeAssignment.id
                    ? 'Withdrawing...'
                    : 'Withdraw assignment'}
                </button>
              ) : null}
            </div>
          ) : null}

          {canAssign ? (
            <AssignmentOfferForm
              technicians={technicians.items}
              hasActiveAssignment={activeAssignment !== undefined}
              isSubmitting={assignmentSubmitting}
              onSubmit={offerAssignment}
              error={null}
            />
          ) : (
            <InlineWarning>
              This work order is not in a state that accepts assignment offers.
            </InlineWarning>
          )}
        </div>
      </section>

      <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <h2 className="text-base font-semibold text-white">
          Completion reports
        </h2>
        <p className="mt-1 text-sm text-slate-400">
          Review evidence submitted by the technician and verify or reject it.
        </p>
        {completionReports.items.length === 0 ? (
          <div className="mt-4">
            <EmptyState
              title="No completion reports"
              description="A completion report will appear here when the technician submits evidence."
            />
          </div>
        ) : (
          <ul className="mt-4 grid gap-3">
            {completionReports.items.map((report) => (
              <li
                key={report.id}
                className="rounded-xl border border-slate-800 bg-slate-950/40 p-4"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <EvidenceStatusBadge status={report.evidence_status} />
                  <span className="text-xs text-slate-500">
                    Submitted {formatDateTime(report.submitted_at)}
                  </span>
                </div>
                <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-200">
                  {report.summary}
                </p>
                <Link
                  to={adminCompletionReportPath(report.id)}
                  className="mt-3 inline-flex text-sm font-medium text-sky-300 hover:text-sky-200"
                >
                  Review completion report
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <h2 className="text-base font-semibold text-white">
          Assignment history
        </h2>
        {assignments.items.length === 0 ? (
          <div className="mt-4">
            <EmptyState
              title="No assignments"
              description="Assignment offers and their outcomes will appear here."
            />
          </div>
        ) : (
          <ul className="mt-4 grid gap-2">
            {assignments.items.map((assignment) => (
              <li
                key={assignment.id}
                className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-800 bg-slate-950/40 p-3"
              >
                <AssignmentStatusBadge status={assignment.assignment_status} />
                <span className="text-xs text-slate-400">
                  Technician {assignment.technician_id}
                </span>
                <span className="text-xs text-slate-500">
                  Offered {formatDateTime(assignment.assigned_at)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <p className="text-xs leading-5 text-slate-500">
        Administrator actions are validated by the API. Cancelling, escalating,
        and completing work orders are irreversible in the current lifecycle.
      </p>
    </div>
  )
}
