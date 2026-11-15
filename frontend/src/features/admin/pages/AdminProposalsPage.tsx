import { useState } from 'react'
import { Link } from 'react-router-dom'
import { EmptyState } from '../../../components/EmptyState'
import { ErrorScreen } from '../../../components/ErrorScreen'
import { FormField, inputClassName } from '../../../components/FormField'
import { LoadingScreen } from '../../../components/LoadingScreen'
import { PageHeader } from '../../../components/PageHeader'
import { useApiClient } from '../../../lib/api/api-client-context'
import { apiErrorMessage } from '../../../lib/api/errors'
import type { WorkOrderProposalStatus } from '../../../lib/api/types'
import { formatDateTime } from '../../../lib/format'
import { useAsyncData } from '../../../lib/hooks/use-async-data'
import { PriorityBadge } from '../../complaints/components/ComplaintBadges'
import { listAdminProposals } from '../api'
import { AdminPagination } from '../components/AdminPagination'
import { ProposalStatusBadge } from '../components/AdminBadges'
import { PROPOSAL_STATUS_LABELS } from '../labels'
import { ADMIN_ROUTES, adminProposalPath } from '../routes'

const PAGE_SIZE = 20

export function AdminProposalsPage() {
  const apiClient = useApiClient()
  const [offset, setOffset] = useState(0)
  const [status, setStatus] = useState<WorkOrderProposalStatus | ''>('')

  const { data, error, isLoading, reload } = useAsyncData(
    (signal) =>
      listAdminProposals(
        apiClient,
        {
          status: status || undefined,
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
        title="Work-order proposals"
        description="Review AI-assisted proposals, compare technician recommendations, and approve or reject them."
      />

      <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <FormField id="admin-proposal-status-filter" label="Status">
          <select
            id="admin-proposal-status-filter"
            className={inputClassName}
            value={status}
            onChange={(event) => {
              setOffset(0)
              setStatus(
                event.target.value as WorkOrderProposalStatus | '',
              )
            }}
          >
            <option value="">All statuses</option>
            {(
              Object.keys(PROPOSAL_STATUS_LABELS) as WorkOrderProposalStatus[]
            ).map((value) => (
              <option key={value} value={value}>
                {PROPOSAL_STATUS_LABELS[value]}
              </option>
            ))}
          </select>
        </FormField>
      </section>

      {isLoading ? (
        <LoadingScreen label="Loading proposals..." />
      ) : error || !data ? (
        <ErrorScreen
          message={apiErrorMessage(error, 'Unable to load proposals.')}
          onRetry={reload}
        />
      ) : data.items.length === 0 ? (
        <EmptyState
          title="No proposals match these filters"
          description="Generate a proposal from a ready complaint to start the review workflow."
          action={
            <Link
              to={ADMIN_ROUTES.complaints}
              className="inline-flex rounded-lg border border-slate-700 px-4 py-2 text-sm font-medium text-slate-200 transition hover:border-slate-500"
            >
              Review complaints
            </Link>
          }
        />
      ) : (
        <>
          <ul className="grid gap-3">
            {data.items.map((proposal) => (
              <li key={proposal.id}>
                <Link
                  to={adminProposalPath(proposal.id)}
                  className="block rounded-2xl border border-slate-800 bg-slate-900/60 p-5 transition hover:border-sky-500/40"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <ProposalStatusBadge status={proposal.status} />
                    <PriorityBadge priority={proposal.priority} />
                    {proposal.requires_escalation ? (
                      <span className="rounded-full border border-rose-500/30 bg-rose-500/10 px-2.5 py-0.5 text-xs font-medium text-rose-300">
                        Escalation required
                      </span>
                    ) : null}
                    <span className="text-xs text-slate-500">
                      Updated {formatDateTime(proposal.updated_at)}
                    </span>
                  </div>
                  <h2 className="mt-3 text-base font-semibold text-white">
                    {proposal.title}
                  </h2>
                  <p className="mt-1 line-clamp-2 text-sm leading-6 text-slate-300">
                    {proposal.proposed_scope}
                  </p>
                  <p className="mt-2 font-mono text-xs text-slate-500">
                    Complaint {proposal.complaint_id}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
          <AdminPagination
            offset={offset}
            pageSize={PAGE_SIZE}
            total={data.total}
            noun="proposals"
            onOffsetChange={setOffset}
          />
        </>
      )}
    </div>
  )
}
