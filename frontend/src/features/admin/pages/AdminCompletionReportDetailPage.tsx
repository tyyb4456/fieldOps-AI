import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ErrorScreen } from '../../../components/ErrorScreen'
import { Notice } from '../../../components/Feedback'
import { LoadingScreen } from '../../../components/LoadingScreen'
import { PageHeader } from '../../../components/PageHeader'
import { useApiClient } from '../../../lib/api/api-client-context'
import { formatDateTime } from '../../../lib/format'
import { useAsyncData } from '../../../lib/hooks/use-async-data'
import { EvidenceStatusBadge } from '../../technicians/components/TechnicianBadges'
import type { CompletionReportUpdateRequest } from '../../work-orders/types'
import {
  getAdminCompletionReport,
  updateAdminCompletionReport,
} from '../api'
import { CompletionVerificationForm } from '../components/CompletionVerificationForm'
import { adminCompletionReportErrorMessage } from '../errors'
import {
  ADMIN_ROUTES,
  adminWorkOrderPath,
} from '../routes'

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

export function AdminCompletionReportDetailPage() {
  const apiClient = useApiClient()
  const { completionReportId = '' } = useParams()
  const [notice, setNotice] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const { data: report, error: loadError, isLoading, reload } = useAsyncData(
    (signal) => getAdminCompletionReport(apiClient, completionReportId, signal),
    [apiClient, completionReportId],
  )

  if (isLoading) {
    return <LoadingScreen label="Loading completion report..." />
  }

  if (loadError || !report) {
    return (
      <ErrorScreen
        message={adminCompletionReportErrorMessage(loadError)}
        onRetry={reload}
      />
    )
  }

  const canVerify = report.evidence_status !== 'verified'

  async function verify(payload: CompletionReportUpdateRequest) {
    if (!report) {
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      await updateAdminCompletionReport(apiClient, report.id, payload)
      setNotice(
        payload.evidence_status === 'verified'
          ? 'Evidence verified.'
          : 'Evidence rejected. The technician can revise the report.',
      )
      reload()
    } catch (caught) {
      setError(adminCompletionReportErrorMessage(caught))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="grid gap-6">
      <PageHeader
        eyebrow="Completion evidence"
        title="Completion report"
        description={`Submitted ${formatDateTime(report.submitted_at)}`}
        actions={
          <Link
            to={ADMIN_ROUTES.completionReports}
            className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-semibold text-slate-200 transition hover:border-slate-500 hover:text-white"
          >
            Back to evidence queue
          </Link>
        }
      />

      {notice ? <Notice>{notice}</Notice> : null}

      <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <div className="flex flex-wrap items-center gap-2">
          <EvidenceStatusBadge status={report.evidence_status} />
          <span className="text-xs text-slate-500">
            Work order {report.work_order_id}
          </span>
        </div>
        <h2 className="mt-4 text-sm font-semibold text-slate-200">Summary</h2>
        <p className="mt-2 whitespace-pre-wrap text-sm leading-7 text-slate-100">
          {report.summary}
        </p>
        {report.verification_notes ? (
          <>
            <h2 className="mt-5 text-sm font-semibold text-slate-200">
              Verification notes
            </h2>
            <p className="mt-2 whitespace-pre-wrap text-sm leading-7 text-slate-300">
              {report.verification_notes}
            </p>
          </>
        ) : null}
        <div className="mt-4 flex flex-wrap gap-4 text-sm">
          <Link
            to={adminWorkOrderPath(report.work_order_id)}
            className="font-medium text-sky-300 hover:text-sky-200"
          >
            View work order
          </Link>
          {report.service_record_id ? (
            <span className="text-xs text-slate-500">
              Service record {report.service_record_id}
            </span>
          ) : (
            <span className="text-xs text-slate-500">
              No service record linked
            </span>
          )}
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <DetailRow label="Report ID" value={report.id} />
        <DetailRow label="Work order ID" value={report.work_order_id} />
        <DetailRow
          label="Service record"
          value={report.service_record_id ?? 'Not linked'}
        />
        <DetailRow
          label="Verified"
          value={
            report.verified_at
              ? formatDateTime(report.verified_at)
              : 'Not verified'
          }
        />
      </section>

      <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <h2 className="text-base font-semibold text-white">
          Verification decision
        </h2>
        {canVerify ? (
          <>
            <p className="mt-1 text-sm leading-6 text-slate-400">
              Verify the evidence to mark it complete, or reject it with notes so
              the technician can correct and resubmit. Verification is final.
            </p>
            <div className="mt-4">
              <CompletionVerificationForm
                initialNotes={report.verification_notes ?? ''}
                canReject={report.evidence_status === 'pending'}
                isSubmitting={submitting}
                onSubmit={verify}
                error={error}
              />
            </div>
          </>
        ) : (
          <>
            <p className="mt-1 text-sm leading-6 text-slate-400">
              This evidence has been verified and is immutable.
            </p>
            <p className="mt-2 text-xs text-slate-500">
              Verified {report.verified_at ? formatDateTime(report.verified_at) : ''}
            </p>
          </>
        )}
      </section>
    </div>
  )
}
