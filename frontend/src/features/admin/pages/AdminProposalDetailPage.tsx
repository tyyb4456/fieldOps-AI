import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ErrorScreen } from '../../../components/ErrorScreen'
import { Notice } from '../../../components/Feedback'
import { LoadingScreen } from '../../../components/LoadingScreen'
import { PageHeader } from '../../../components/PageHeader'
import { useApiClient } from '../../../lib/api/api-client-context'
import { formatDateTime } from '../../../lib/format'
import { useAsyncData } from '../../../lib/hooks/use-async-data'
import { PriorityBadge } from '../../complaints/components/ComplaintBadges'
import type { Citation } from '../../knowledge/types'
import {
  approveAdminProposal,
  getAdminProposal,
  rejectAdminProposal,
} from '../api'
import {
  DiagnosticStatusBadge,
  ProposalStatusBadge,
} from '../components/AdminBadges'
import { ProposalDecisionPanel } from '../components/ProposalDecisionPanel'
import { adminProposalErrorMessage } from '../errors'
import { ADMIN_ROUTES, adminComplaintPath } from '../routes'

function SectionList({
  title,
  items,
}: {
  title: string
  items: readonly string[]
}) {
  if (items.length === 0) {
    return null
  }
  return (
    <div>
      <h3 className="text-sm font-semibold text-slate-200">{title}</h3>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-300">
        {items.map((item, index) => (
          <li key={`${index}-${item}`}>{item}</li>
        ))}
      </ul>
    </div>
  )
}

function CitationItem({ citation }: { citation: Citation }) {
  return (
    <li className="rounded-xl border border-slate-800 bg-slate-950/40 p-3">
      <p className="text-sm font-medium text-slate-200">
        {citation.document_name}
      </p>
      <p className="mt-1 text-xs text-slate-500">
        {citation.manufacturer} {citation.model}
        {citation.version ? ` - v${citation.version}` : ''}
        {citation.page_number ? ` - page ${citation.page_number}` : ''}
      </p>
      <p className="mt-2 line-clamp-3 text-xs leading-5 text-slate-400">
        {citation.excerpt}
      </p>
    </li>
  )
}

export function AdminProposalDetailPage() {
  const apiClient = useApiClient()
  const { proposalId = '' } = useParams()
  const [notice, setNotice] = useState<string | null>(null)
  const [decisionSubmitting, setDecisionSubmitting] = useState(false)
  const [decisionError, setDecisionError] = useState<string | null>(null)

  const { data: proposal, error, isLoading, reload } = useAsyncData(
    (signal) => getAdminProposal(apiClient, proposalId, signal),
    [apiClient, proposalId],
  )

  if (isLoading) {
    return <LoadingScreen label="Loading proposal..." />
  }

  if (error || !proposal) {
    return (
      <ErrorScreen
        message={adminProposalErrorMessage(error)}
        onRetry={reload}
      />
    )
  }

  async function approve(technicianId: string | null) {
    if (!proposal) {
      return
    }
    setDecisionSubmitting(true)
    setDecisionError(null)
    try {
      await approveAdminProposal(apiClient, proposal.id, technicianId)
      setNotice('Proposal approved and work order created.')
      reload()
    } catch (caught) {
      setDecisionError(adminProposalErrorMessage(caught))
    } finally {
      setDecisionSubmitting(false)
    }
  }

  async function reject(reason: string) {
    if (!proposal) {
      return
    }
    setDecisionSubmitting(true)
    setDecisionError(null)
    try {
      await rejectAdminProposal(apiClient, proposal.id, reason)
      setNotice('Proposal rejected.')
      reload()
    } catch (caught) {
      setDecisionError(adminProposalErrorMessage(caught))
    } finally {
      setDecisionSubmitting(false)
    }
  }

  return (
    <div className="grid gap-6">
      <PageHeader
        eyebrow="Proposal"
        title={proposal.title}
        description={`Complaint ${proposal.complaint_id} - created ${formatDateTime(
          proposal.created_at,
        )}`}
        actions={
          <Link
            to={ADMIN_ROUTES.proposals}
            className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-semibold text-slate-200 transition hover:border-slate-500 hover:text-white"
          >
            Back to proposals
          </Link>
        }
      />

      {notice ? <Notice>{notice}</Notice> : null}

      <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <div className="flex flex-wrap items-center gap-2">
          <ProposalStatusBadge status={proposal.status} />
          <PriorityBadge priority={proposal.priority} />
          <DiagnosticStatusBadge status={proposal.diagnostic_status} />
          {proposal.requires_escalation ? (
            <span className="rounded-full border border-rose-500/30 bg-rose-500/10 px-2.5 py-0.5 text-xs font-medium text-rose-300">
              Escalation required
            </span>
          ) : null}
        </div>

        {proposal.requires_escalation && proposal.escalation_reason ? (
          <p className="mt-3 rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-200">
            {proposal.escalation_reason}
          </p>
        ) : null}

        <div className="mt-4 grid gap-3 text-sm">
          <Link
            to={adminComplaintPath(proposal.complaint_id)}
            className="font-medium text-sky-300 hover:text-sky-200"
          >
            View complaint
          </Link>
          {proposal.resulting_work_order_id ? (
            <Link
              to={`${ADMIN_ROUTES.workOrders}/${encodeURIComponent(
                proposal.resulting_work_order_id,
              )}`}
              className="font-medium text-sky-300 hover:text-sky-200"
            >
              View resulting work order
            </Link>
          ) : null}
          <span className="text-xs text-slate-500">
            Last updated {formatDateTime(proposal.updated_at)}
          </span>
        </div>
      </section>

      {proposal.status === 'pending_approval' ? (
        <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
          <h2 className="text-base font-semibold text-white">
            Review decision
          </h2>
          <p className="mt-1 text-sm text-slate-400">
            Approval converts the proposal into a work order. Optionally offer
            the assignment to an eligible recommended technician.
          </p>
          <div className="mt-4">
            <ProposalDecisionPanel
              proposal={proposal}
              isSubmitting={decisionSubmitting}
              onApprove={approve}
              onReject={reject}
              error={decisionError}
            />
          </div>
        </section>
      ) : null}

      {proposal.status === 'rejected' && proposal.rejection_reason ? (
        <section className="rounded-2xl border border-rose-500/30 bg-rose-500/5 p-5">
          <h2 className="text-base font-semibold text-rose-200">
            Rejection reason
          </h2>
          <p className="mt-2 whitespace-pre-wrap text-sm text-slate-200">
            {proposal.rejection_reason}
          </p>
          {proposal.reviewed_at ? (
            <p className="mt-2 text-xs text-slate-500">
              Reviewed {formatDateTime(proposal.reviewed_at)}
            </p>
          ) : null}
        </section>
      ) : null}

      <section className="grid gap-5 rounded-2xl border border-slate-800 bg-slate-900/60 p-5 lg:grid-cols-2">
        <div>
          <h2 className="text-sm font-semibold text-slate-200">
            Problem description
          </h2>
          <p className="mt-2 whitespace-pre-wrap text-sm leading-7 text-slate-100">
            {proposal.problem_description}
          </p>
        </div>
        <div>
          <h2 className="text-sm font-semibold text-slate-200">
            Proposed scope
          </h2>
          <p className="mt-2 whitespace-pre-wrap text-sm leading-7 text-slate-100">
            {proposal.proposed_scope}
          </p>
        </div>
        <div>
          <h2 className="text-sm font-semibold text-slate-200">
            Technical findings
          </h2>
          <p className="mt-2 whitespace-pre-wrap text-sm leading-7 text-slate-100">
            {proposal.technical_findings}
          </p>
        </div>
        <div className="grid gap-4">
          <SectionList
            title="Recommended actions"
            items={proposal.recommended_actions}
          />
          <SectionList
            title="Required skills"
            items={proposal.required_skills}
          />
          <SectionList
            title="Required parts"
            items={proposal.required_parts}
          />
          <SectionList
            title="Safety warnings"
            items={proposal.safety_warnings}
          />
          <SectionList
            title="Missing information"
            items={proposal.missing_information}
          />
          <SectionList
            title="Generation warnings"
            items={proposal.generation_warnings}
          />
        </div>
      </section>

      <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <h2 className="text-base font-semibold text-white">
          Technician recommendations
        </h2>
        {proposal.technician_recommendations.length === 0 ? (
          <p className="mt-2 text-sm text-slate-500">
            No technician recommendations were generated.
          </p>
        ) : (
          <ul className="mt-4 grid gap-3">
            {proposal.technician_recommendations.map((recommendation) => (
              <li
                key={recommendation.technician_id}
                className="rounded-xl border border-slate-800 bg-slate-950/40 p-4"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-semibold text-slate-100">
                    Rank {recommendation.rank}: {recommendation.full_name}
                  </span>
                  <span
                    className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${
                      recommendation.eligible
                        ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                        : 'border-slate-700 bg-slate-800/70 text-slate-300'
                    }`}
                  >
                    {recommendation.eligible ? 'Eligible' : 'Not eligible'}
                  </span>
                  <span className="text-xs text-slate-500">
                    Workload {recommendation.active_workload} -{' '}
                    {recommendation.availability_status}
                  </span>
                </div>
                {recommendation.matching_skills.length > 0 ? (
                  <p className="mt-2 text-xs text-slate-400">
                    Matching skills: {recommendation.matching_skills.join(', ')}
                  </p>
                ) : null}
                {recommendation.missing_skills.length > 0 ? (
                  <p className="mt-1 text-xs text-slate-400">
                    Missing skills: {recommendation.missing_skills.join(', ')}
                  </p>
                ) : null}
                {recommendation.reasons.length > 0 ? (
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-slate-400">
                    {recommendation.reasons.map((reason, index) => (
                      <li key={`${index}-${reason}`}>{reason}</li>
                    ))}
                  </ul>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <h2 className="text-base font-semibold text-white">Citations</h2>
        <p className="mt-1 text-sm text-slate-400">
          Diagnostic summary: {proposal.diagnostic_summary}
        </p>
        {proposal.citations.length === 0 ? (
          <p className="mt-2 text-sm text-slate-500">
            No citations were attached to this proposal.
          </p>
        ) : (
          <ul className="mt-4 grid gap-3">
            {proposal.citations.map((citation) => (
              <CitationItem
                key={`${citation.source_id}-${citation.chunk_id}`}
                citation={citation}
              />
            ))}
          </ul>
        )}
      </section>

      <p className="text-xs leading-5 text-slate-500">
        Proposals are snapshots. If the complaint changes after generation, the
        API may reject the decision as stale and require a new proposal. Review
        the latest complaint and citations before approving.
      </p>
    </div>
  )
}
