import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { EmptyState } from '../../../components/EmptyState'
import { ErrorScreen } from '../../../components/ErrorScreen'
import { InlineWarning, Notice } from '../../../components/Feedback'
import { LoadingScreen } from '../../../components/LoadingScreen'
import { PageHeader } from '../../../components/PageHeader'
import { useApiClient } from '../../../lib/api/api-client-context'
import type { PaginatedResponse } from '../../../lib/api/types'
import { formatDateTime, formatSymptom } from '../../../lib/format'
import { useAsyncData } from '../../../lib/hooks/use-async-data'
import { listAssignments } from '../../assignments/api'
import type { Assignment } from '../../assignments/types'
import { PriorityBadge } from '../../complaints/components/ComplaintBadges'
import {
  createCompletionReport,
  createServiceRecord,
  getWorkOrder,
  listWorkOrderCompletionReports,
  listWorkOrderServiceRecords,
  updateCompletionReport,
} from '../../work-orders/api'
import type {
  CompletionReport,
  ServiceRecord,
  WorkOrder,
} from '../../work-orders/types'
import { AssignmentActions } from '../components/AssignmentActions'
import {
  CompletionReportCreateForm,
  CompletionReportEditForm,
} from '../components/CompletionReportForm'
import { ServiceRecordForm } from '../components/ServiceRecordForm'
import {
  AssignmentStatusBadge,
  EvidenceStatusBadge,
  WorkOrderStatusBadge,
} from '../components/TechnicianBadges'
import { WorkOrderStatusActions } from '../components/WorkOrderStatusActions'
import {
  completionReportErrorMessage,
  serviceRecordErrorMessage,
  workOrderDetailErrorMessage,
} from '../errors'
import {
  canModifyCompletionReports,
  getTechnicianLifecycle,
} from '../lifecycle'
import { EMPTY_SERVICE_RECORD_FORM } from '../validation'
import {
  TECHNICIAN_ROUTES,
  technicianServiceRecordPath,
} from '../routes'

const DETAIL_PAGE_SIZE = 100

interface WorkOrderDetailData {
  workOrder: WorkOrder
  assignments: PaginatedResponse<Assignment>
  serviceRecords: PaginatedResponse<ServiceRecord>
  completionReports: PaginatedResponse<CompletionReport>
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

function hasWorkPerformed(record: ServiceRecord): boolean {
  return Boolean(record.work_performed?.trim())
}

export function TechnicianWorkOrderDetailPage() {
  const apiClient = useApiClient()
  const navigate = useNavigate()
  const { workOrderId = '' } = useParams()
  const [notice, setNotice] = useState<string | null>(null)
  const [showServiceRecordForm, setShowServiceRecordForm] = useState(false)
  const [serviceRecordSubmitting, setServiceRecordSubmitting] = useState(false)
  const [completionReportSubmitting, setCompletionReportSubmitting] =
    useState(false)
  const [editingReportId, setEditingReportId] = useState<string | null>(null)

  const { data, error, isLoading, reload } =
    useAsyncData<WorkOrderDetailData>(
      async (signal) => {
        const [workOrder, assignments, serviceRecords, completionReports] =
          await Promise.all([
            getWorkOrder(apiClient, workOrderId, signal),
            listAssignments(
              apiClient,
              { work_order_id: workOrderId, limit: DETAIL_PAGE_SIZE },
              signal,
            ),
            listWorkOrderServiceRecords(
              apiClient,
              workOrderId,
              { limit: DETAIL_PAGE_SIZE },
              signal,
            ),
            listWorkOrderCompletionReports(
              apiClient,
              workOrderId,
              { limit: DETAIL_PAGE_SIZE },
              signal,
            ),
          ])
        return { workOrder, assignments, serviceRecords, completionReports }
      },
      [apiClient, workOrderId],
    )

  if (isLoading) {
    return <LoadingScreen label="Loading work-order details..." />
  }

  if (error || !data) {
    return (
      <ErrorScreen
        message={workOrderDetailErrorMessage(error)}
        onRetry={reload}
      />
    )
  }

  const { workOrder, assignments, serviceRecords, completionReports } = data
  const offeredAssignment = assignments.items.find(
    (assignment) => assignment.assignment_status === 'offered',
  )
  const acceptedAssignment = assignments.items.find(
    (assignment) => assignment.assignment_status === 'accepted',
  )
  const eligibleServiceRecords = serviceRecords.items.filter(hasWorkPerformed)
  const lifecycle = getTechnicianLifecycle({
    workOrderStatus: workOrder.status,
    hasOfferedAssignment: offeredAssignment !== undefined,
    hasAcceptedAssignment: acceptedAssignment !== undefined,
    hasServiceRecord: serviceRecords.total > 0,
    hasEligibleServiceRecord: eligibleServiceRecords.length > 0,
  })

  async function submitServiceRecord(
    payload: Parameters<typeof createServiceRecord>[2],
  ) {
    setServiceRecordSubmitting(true)
    try {
      await createServiceRecord(apiClient, workOrder.id, payload)
      setShowServiceRecordForm(false)
      setNotice('Service record added to this work order.')
      reload()
    } finally {
      setServiceRecordSubmitting(false)
    }
  }

  async function submitCompletionReport(
    payload: Parameters<typeof createCompletionReport>[2],
  ) {
    setCompletionReportSubmitting(true)
    try {
      await createCompletionReport(apiClient, workOrder.id, payload)
      setNotice('Completion report submitted for verification.')
      reload()
    } finally {
      setCompletionReportSubmitting(false)
    }
  }

  async function saveCompletionReport(
    reportId: string,
    payload: Parameters<typeof updateCompletionReport>[2],
  ) {
    setCompletionReportSubmitting(true)
    try {
      await updateCompletionReport(apiClient, reportId, payload)
      setEditingReportId(null)
      setNotice('Completion report summary updated.')
      reload()
    } finally {
      setCompletionReportSubmitting(false)
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
            to={TECHNICIAN_ROUTES.workOrders}
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
          {acceptedAssignment ? (
            <AssignmentStatusBadge status="accepted" />
          ) : offeredAssignment ? (
            <AssignmentStatusBadge status="offered" />
          ) : null}
        </div>

        <p className="mt-3 text-sm leading-6 text-slate-300">
          {lifecycle.message}
        </p>

        <h2 className="mt-5 text-sm font-semibold text-slate-200">
          Work description
        </h2>
        <p className="mt-2 whitespace-pre-wrap text-sm leading-7 text-slate-100">
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
      </section>

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <DetailRow label="Work order ID" value={workOrder.id} />
        <DetailRow label="Complaint ID" value={workOrder.complaint_id} />
        <DetailRow label="Equipment ID" value={workOrder.equipment_id} />
        <DetailRow
          label="Offered"
          value={
            offeredAssignment
              ? formatDateTime(offeredAssignment.assigned_at)
              : 'Not offered'
          }
        />
        <DetailRow
          label="Accepted"
          value={
            acceptedAssignment?.accepted_at
              ? formatDateTime(acceptedAssignment.accepted_at)
              : 'Not accepted'
          }
        />
        <DetailRow
          label="Last updated"
          value={formatDateTime(workOrder.updated_at)}
        />
      </section>

      {offeredAssignment ? (
        <section className="rounded-2xl border border-amber-400/30 bg-amber-400/5 p-5">
          <h2 className="text-base font-semibold text-white">
            Assignment offer
          </h2>
          <p className="mt-1 text-sm text-slate-300">
            Accept this offer to start work and record service activity.
          </p>
          <div className="mt-4">
            <AssignmentActions
              assignment={offeredAssignment}
              onUpdated={(_updated, action) => {
                if (action === 'rejected') {
                  navigate(TECHNICIAN_ROUTES.assignments, {
                    state: {
                      notice:
                        'Assignment rejected. The service team can reassign it.',
                    },
                  })
                  return
                }
                setNotice('Assignment accepted. You can start work now.')
                reload()
              }}
            />
          </div>
        </section>
      ) : null}

      {lifecycle.canStartWork ||
      lifecycle.canMarkAwaitingParts ||
      lifecycle.canSubmitForVerification ||
      lifecycle.canEscalate ||
      lifecycle.canResumeWork ? (
        <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
          <h2 className="text-base font-semibold text-white">Work actions</h2>
          <p className="mt-1 text-sm text-slate-400">
            Status changes are validated by the API. Completion is confirmed by
            an administrator after evidence verification.
          </p>
          <div className="mt-4">
            <WorkOrderStatusActions
              workOrderId={workOrder.id}
              lifecycle={lifecycle}
              onUpdated={(updated) => {
                setNotice(
                  `Work order moved to ${updated.status.replaceAll('_', ' ')}.`,
                )
                reload()
              }}
            />
          </div>
        </section>
      ) : null}

      <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-white">
              Service records
            </h2>
            <p className="mt-1 text-xs text-slate-500">
              {serviceRecords.total} record
              {serviceRecords.total === 1 ? '' : 's'} for this work order
            </p>
          </div>
          {lifecycle.canCreateServiceRecord && !showServiceRecordForm ? (
            <button
              type="button"
              onClick={() => setShowServiceRecordForm(true)}
              className="rounded-xl bg-sky-500 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-sky-400"
            >
              Add service record
            </button>
          ) : null}
        </div>

        {showServiceRecordForm && lifecycle.canCreateServiceRecord ? (
          <div className="mt-4 rounded-xl border border-slate-800 bg-slate-950/40 p-4">
            <ServiceRecordForm
              initial={EMPTY_SERVICE_RECORD_FORM}
              submitLabel="Save service record"
              isSubmitting={serviceRecordSubmitting}
              onSubmit={submitServiceRecord}
              onCancel={() => setShowServiceRecordForm(false)}
              errorMessage={serviceRecordErrorMessage}
            />
          </div>
        ) : null}

        {serviceRecords.items.length === 0 ? (
          <div className="mt-4">
            <EmptyState
              title="No service records"
              description={
                lifecycle.canCreateServiceRecord
                  ? 'Add a service record to document findings, work performed, and parts used.'
                  : 'Service records can be added after you accept the assignment and while the work order is accepted, in progress, or awaiting parts.'
              }
            />
          </div>
        ) : (
          <ul className="mt-4 grid gap-3">
            {serviceRecords.items.map((record) => (
              <li key={record.id}>
                <Link
                  to={technicianServiceRecordPath(record.id)}
                  className="block rounded-xl border border-slate-800 bg-slate-950/40 p-4 transition hover:border-sky-500/40"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-xs text-slate-500">
                      Recorded {formatDateTime(record.recorded_at)}
                    </span>
                    <span className="text-xs text-slate-500">
                      {record.parts_used.length} part
                      {record.parts_used.length === 1 ? '' : 's'} used
                    </span>
                  </div>
                  <p className="mt-2 line-clamp-2 text-sm leading-6 text-slate-200">
                    {record.work_performed ?? record.findings ?? 'No details provided.'}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        )}

        {serviceRecords.total > serviceRecords.items.length ? (
          <p className="mt-3 text-xs text-slate-500">
            Showing {serviceRecords.items.length} of {serviceRecords.total}{' '}
            service records in this view.
          </p>
        ) : null}
      </section>

      <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-white">
              Completion reports
            </h2>
            <p className="mt-1 text-xs text-slate-500">
              Reports are submitted for administrator verification.
            </p>
          </div>
        </div>

        {completionReports.items.length > 0 ? (
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
                {editingReportId === report.id ? (
                  <div className="mt-3">
                    <CompletionReportEditForm
                      initialSummary={report.summary}
                      isSubmitting={completionReportSubmitting}
                      onSubmit={(payload) =>
                        saveCompletionReport(report.id, payload)
                      }
                      onCancel={() => setEditingReportId(null)}
                      errorMessage={completionReportErrorMessage}
                    />
                  </div>
                ) : (
                  <>
                    <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-200">
                      {report.summary}
                    </p>
                    {report.verification_notes ? (
                      <p className="mt-2 text-xs leading-5 text-amber-200">
                        Verification notes: {report.verification_notes}
                      </p>
                    ) : null}
                    {report.verified_at ? (
                      <p className="mt-2 text-xs text-slate-500">
                        Verified {formatDateTime(report.verified_at)}
                      </p>
                    ) : null}
                    {report.evidence_status === 'pending' &&
                    canModifyCompletionReports(workOrder.status) ? (
                      <button
                        type="button"
                        onClick={() => setEditingReportId(report.id)}
                        className="mt-3 rounded-lg border border-slate-700 px-3 py-2 text-xs font-medium text-slate-200 transition hover:border-slate-500"
                      >
                        Edit summary
                      </button>
                    ) : (
                      <p className="mt-3 text-xs text-slate-500">
                        {report.evidence_status === 'pending'
                          ? 'This report is read-only because the work order is no longer in an editable state.'
                          : 'Verified or rejected reports are read-only for technicians.'}
                      </p>
                    )}
                  </>
                )}
              </li>
            ))}
          </ul>
        ) : null}

        {completionReports.total === 0 ? (
          lifecycle.canCreateCompletionReport ? (
            <div className="mt-4 rounded-xl border border-slate-800 bg-slate-950/40 p-4">
              <h3 className="text-sm font-semibold text-white">
                Submit completion report
              </h3>
              <p className="mt-1 text-xs leading-5 text-slate-500">
                Choose a service record with work performed. A work order can
                have one completion report.
              </p>
              <div className="mt-4">
                <CompletionReportCreateForm
                  serviceRecords={eligibleServiceRecords}
                  isSubmitting={completionReportSubmitting}
                  onSubmit={submitCompletionReport}
                  errorMessage={completionReportErrorMessage}
                />
              </div>
            </div>
          ) : (
            <div className="mt-4">
              <InlineWarning>
                {eligibleServiceRecords.length === 0
                  ? 'Add a service record with work performed before submitting a completion report.'
                  : 'A completion report can be submitted while the work order is accepted, in progress, awaiting parts, or pending verification.'}
              </InlineWarning>
            </div>
          )
        ) : null}
      </section>

      <p className="text-xs leading-5 text-slate-500">
        This technician view exposes work-order identifiers only. Equipment
        details, customer contact information, and complaint detail endpoints
        are not available to the technician role. Service-record and
        completion-report actions require an accepted assignment and the API
        remains the authority for lifecycle validation.
      </p>
    </div>
  )
}
