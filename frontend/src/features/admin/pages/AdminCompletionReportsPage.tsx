import { useState } from 'react'
import { Link } from 'react-router-dom'
import { EmptyState } from '../../../components/EmptyState'
import { ErrorScreen } from '../../../components/ErrorScreen'
import { FormField, inputClassName } from '../../../components/FormField'
import { LoadingScreen } from '../../../components/LoadingScreen'
import { PageHeader } from '../../../components/PageHeader'
import { useApiClient } from '../../../lib/api/api-client-context'
import { apiErrorMessage } from '../../../lib/api/errors'
import type { EvidenceStatus } from '../../../lib/api/types'
import { formatDateTime } from '../../../lib/format'
import { useAsyncData } from '../../../lib/hooks/use-async-data'
import { EvidenceStatusBadge } from '../../technicians/components/TechnicianBadges'
import { EVIDENCE_STATUS_LABELS } from '../../technicians/labels'
import { listAdminCompletionReports } from '../api'
import { AdminPagination } from '../components/AdminPagination'
import {
  adminCompletionReportPath,
  adminWorkOrderPath,
} from '../routes'

const PAGE_SIZE = 20

export function AdminCompletionReportsPage() {
  const apiClient = useApiClient()
  const [offset, setOffset] = useState(0)
  const [status, setStatus] = useState<EvidenceStatus | ''>('pending')

  const { data, error, isLoading, reload } = useAsyncData(
    (signal) =>
      listAdminCompletionReports(
        apiClient,
        {
          evidence_status: status || undefined,
          limit: PAGE_SIZE,
          offset,
        },
        signal,
      ),
    [apiClient, offset, status],
  )

  return (
    <div className="grid gap-6">
      <PageHeader
        eyebrow="Administrator"
        title="Completion evidence"
        description="Review completion reports submitted by technicians, verify supporting evidence, or reject it with notes."
      />

      <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <FormField
          id="admin-completion-status-filter"
          label="Evidence status"
        >
          <select
            id="admin-completion-status-filter"
            className={inputClassName}
            value={status}
            onChange={(event) => {
              setOffset(0)
              setStatus(event.target.value as EvidenceStatus | '')
            }}
          >
            <option value="">All statuses</option>
            {(
              Object.keys(EVIDENCE_STATUS_LABELS) as EvidenceStatus[]
            ).map((value) => (
              <option key={value} value={value}>
                {EVIDENCE_STATUS_LABELS[value]}
              </option>
            ))}
          </select>
        </FormField>
      </section>

      {isLoading ? (
        <LoadingScreen label="Loading completion reports..." />
      ) : error || !data ? (
        <ErrorScreen
          message={apiErrorMessage(
            error,
            'Unable to load completion reports.',
          )}
          onRetry={reload}
        />
      ) : data.items.length === 0 ? (
        <EmptyState
          title="No completion reports match these filters"
          description="Technicians submit completion evidence from their work-order detail pages."
        />
      ) : (
        <>
          <ul className="grid gap-3">
            {data.items.map((report) => (
              <li
                key={report.id}
                className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <EvidenceStatusBadge status={report.evidence_status} />
                  <span className="text-xs text-slate-500">
                    Submitted {formatDateTime(report.submitted_at)}
                  </span>
                  {report.verified_at ? (
                    <span className="text-xs text-slate-500">
                      Verified {formatDateTime(report.verified_at)}
                    </span>
                  ) : null}
                </div>
                <p className="mt-3 line-clamp-3 whitespace-pre-wrap text-sm leading-6 text-slate-100">
                  {report.summary}
                </p>
                <div className="mt-4 flex flex-wrap gap-4 text-sm">
                  <Link
                    to={adminCompletionReportPath(report.id)}
                    className="font-medium text-sky-300 hover:text-sky-200"
                  >
                    Review evidence
                  </Link>
                  <Link
                    to={adminWorkOrderPath(report.work_order_id)}
                    className="font-medium text-sky-300 hover:text-sky-200"
                  >
                    View work order
                  </Link>
                </div>
              </li>
            ))}
          </ul>
          <AdminPagination
            offset={offset}
            pageSize={PAGE_SIZE}
            total={data.total}
            noun="reports"
            onOffsetChange={setOffset}
          />
        </>
      )}
    </div>
  )
}
