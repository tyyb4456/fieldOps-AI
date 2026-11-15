import { Link } from 'react-router-dom'
import { EmptyState } from '../../../components/EmptyState'
import { ErrorScreen } from '../../../components/ErrorScreen'
import { LoadingScreen } from '../../../components/LoadingScreen'
import { PageHeader } from '../../../components/PageHeader'
import { useApiClient } from '../../../lib/api/api-client-context'
import { apiErrorMessage } from '../../../lib/api/errors'
import { formatDateTime } from '../../../lib/format'
import { useAsyncData } from '../../../lib/hooks/use-async-data'
import { ComplaintStatusBadge, PriorityBadge } from '../../complaints/components/ComplaintBadges'
import { WorkOrderStatusBadge } from '../../technicians/components/TechnicianBadges'
import {
  loadAdminDashboard,
  selectAdminDashboardPreviews,
  summarizeAdminDashboard,
} from '../dashboard'
import { ProposalStatusBadge } from '../components/AdminBadges'
import {
  ADMIN_ROUTES,
  adminComplaintPath,
  adminProposalPath,
  adminWorkOrderPath,
} from '../routes'

function SummaryCard({
  label,
  value,
  hint,
  to,
}: {
  label: string
  value: number
  hint?: string | null
  to?: string
}) {
  const content = (
    <>
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-2 text-3xl font-semibold text-white">{value}</p>
      {hint ? <p className="mt-2 text-xs text-slate-500">{hint}</p> : null}
    </>
  )

  if (!to) {
    return (
      <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        {content}
      </div>
    )
  }

  return (
    <Link
      to={to}
      className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5 transition hover:border-sky-500/40"
    >
      {content}
    </Link>
  )
}

export function AdminDashboardPage() {
  const apiClient = useApiClient()
  const { data, error, isLoading, reload } = useAsyncData(
    (signal) => loadAdminDashboard(apiClient, signal),
    [apiClient],
  )

  return (
    <div className="grid gap-6">
      <PageHeader
        eyebrow="Administrator workspace"
        title="Operations dashboard"
        description="Triage complaints, review proposals and evidence, coordinate assignments, and keep technical documents ready for retrieval."
      />

      {isLoading ? (
        <LoadingScreen label="Loading the operations dashboard..." />
      ) : error || !data ? (
        <ErrorScreen
          message={apiErrorMessage(
            error,
            'Unable to load the administrator dashboard.',
          )}
          onRetry={reload}
        />
      ) : (
        <>
          <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <SummaryCard
              label="Complaints"
              value={summarizeAdminDashboard(data).complaintTotal}
              to={ADMIN_ROUTES.complaints}
            />
            <SummaryCard
              label="Work orders"
              value={summarizeAdminDashboard(data).workOrderTotal}
              hint={`${summarizeAdminDashboard(data).activeWorkOrderTotal} active in loaded view`}
              to={ADMIN_ROUTES.workOrders}
            />
            <SummaryCard
              label="Proposals awaiting approval"
              value={summarizeAdminDashboard(data).pendingProposalTotal}
              to={ADMIN_ROUTES.proposals}
            />
            <SummaryCard
              label="Evidence awaiting verification"
              value={summarizeAdminDashboard(data).pendingEvidenceTotal}
              to={ADMIN_ROUTES.completionReports}
            />
            <SummaryCard
              label="Running workflows"
              value={summarizeAdminDashboard(data).runningWorkflowTotal}
              to={ADMIN_ROUTES.workflows}
            />
            <SummaryCard
              label="Failed workflows"
              value={summarizeAdminDashboard(data).failedWorkflowTotal}
              to={ADMIN_ROUTES.workflows}
            />
            <SummaryCard
              label="Eligible technicians"
              value={summarizeAdminDashboard(data).eligibleTechnicianTotal}
              to={ADMIN_ROUTES.technicians}
            />
            <SummaryCard
              label="Documents"
              value={summarizeAdminDashboard(data).documentTotal}
              hint={`${summarizeAdminDashboard(data).activeDocumentCount} active in loaded view`}
              to={ADMIN_ROUTES.documents}
            />
          </section>

          {summarizeAdminDashboard(data).workOrderTruncatedNote ? (
            <p className="text-xs text-slate-500">
              {summarizeAdminDashboard(data).workOrderTruncatedNote}
            </p>
          ) : null}

          {summarizeAdminDashboard(data).documentTruncatedNote ? (
            <p className="text-xs text-slate-500">
              {summarizeAdminDashboard(data).documentTruncatedNote}
            </p>
          ) : null}

          <div className="grid gap-6 lg:grid-cols-3">
            <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
              <div className="flex items-center justify-between gap-3">
                <h2 className="text-base font-semibold text-white">
                  Recent complaints
                </h2>
                <Link
                  to={ADMIN_ROUTES.complaints}
                  className="text-xs font-medium text-sky-300 hover:text-sky-200"
                >
                  View all
                </Link>
              </div>
              {selectAdminDashboardPreviews(data).complaints.length === 0 ? (
                <div className="mt-4">
                  <EmptyState
                    title="No complaints"
                    description="New complaints will appear here for triage."
                  />
                </div>
              ) : (
                <ul className="mt-4 grid gap-2">
                  {selectAdminDashboardPreviews(data).complaints.map(
                    (complaint) => (
                      <li key={complaint.id}>
                        <Link
                          to={adminComplaintPath(complaint.id)}
                          className="block rounded-xl border border-slate-800 bg-slate-950/40 p-3 transition hover:border-sky-500/40"
                        >
                          <div className="flex flex-wrap items-center gap-2">
                            <ComplaintStatusBadge status={complaint.status} />
                            <PriorityBadge priority={complaint.priority} />
                          </div>
                          <p className="mt-2 line-clamp-2 text-sm text-slate-200">
                            {complaint.description}
                          </p>
                          <p className="mt-1 text-xs text-slate-500">
                            {formatDateTime(complaint.created_at)}
                          </p>
                        </Link>
                      </li>
                    ),
                  )}
                </ul>
              )}
            </section>

            <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
              <div className="flex items-center justify-between gap-3">
                <h2 className="text-base font-semibold text-white">
                  Recent work orders
                </h2>
                <Link
                  to={ADMIN_ROUTES.workOrders}
                  className="text-xs font-medium text-sky-300 hover:text-sky-200"
                >
                  View all
                </Link>
              </div>
              {selectAdminDashboardPreviews(data).workOrders.length === 0 ? (
                <div className="mt-4">
                  <EmptyState
                    title="No work orders"
                    description="Convert an eligible complaint to create the first work order."
                  />
                </div>
              ) : (
                <ul className="mt-4 grid gap-2">
                  {selectAdminDashboardPreviews(data).workOrders.map(
                    (workOrder) => (
                      <li key={workOrder.id}>
                        <Link
                          to={adminWorkOrderPath(workOrder.id)}
                          className="block rounded-xl border border-slate-800 bg-slate-950/40 p-3 transition hover:border-sky-500/40"
                        >
                          <div className="flex flex-wrap items-center gap-2">
                            <WorkOrderStatusBadge status={workOrder.status} />
                            <PriorityBadge priority={workOrder.priority} />
                          </div>
                          <p className="mt-2 text-sm font-medium text-slate-200">
                            {workOrder.title}
                          </p>
                          <p className="mt-1 text-xs text-slate-500">
                            Updated {formatDateTime(workOrder.updated_at)}
                          </p>
                        </Link>
                      </li>
                    ),
                  )}
                </ul>
              )}
            </section>

            <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
              <div className="flex items-center justify-between gap-3">
                <h2 className="text-base font-semibold text-white">
                  Recent proposals
                </h2>
                <Link
                  to={ADMIN_ROUTES.proposals}
                  className="text-xs font-medium text-sky-300 hover:text-sky-200"
                >
                  View all
                </Link>
              </div>
              {selectAdminDashboardPreviews(data).proposals.length === 0 ? (
                <div className="mt-4">
                  <EmptyState
                    title="No proposals"
                    description="Generate a proposal from a ready complaint to review AI-assisted scope and recommendations."
                  />
                </div>
              ) : (
                <ul className="mt-4 grid gap-2">
                  {selectAdminDashboardPreviews(data).proposals.map(
                    (proposal) => (
                      <li key={proposal.id}>
                        <Link
                          to={adminProposalPath(proposal.id)}
                          className="block rounded-xl border border-slate-800 bg-slate-950/40 p-3 transition hover:border-sky-500/40"
                        >
                          <div className="flex flex-wrap items-center gap-2">
                            <ProposalStatusBadge status={proposal.status} />
                            <PriorityBadge priority={proposal.priority} />
                          </div>
                          <p className="mt-2 text-sm font-medium text-slate-200">
                            {proposal.title}
                          </p>
                          <p className="mt-1 text-xs text-slate-500">
                            Updated {formatDateTime(proposal.updated_at)}
                          </p>
                        </Link>
                      </li>
                    ),
                  )}
                </ul>
              )}
            </section>
          </div>

          <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
            <h2 className="text-base font-semibold text-white">
              Administrative actions
            </h2>
            <p className="mt-1 text-sm text-slate-400">
              Jump to the workspace that matches the next operational decision.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <Link
                to={ADMIN_ROUTES.complaints}
                className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-medium text-slate-200 transition hover:border-sky-500/60 hover:text-white"
              >
                Triage complaints
              </Link>
              <Link
                to={ADMIN_ROUTES.proposals}
                className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-medium text-slate-200 transition hover:border-sky-500/60 hover:text-white"
              >
                Review proposals
              </Link>
              <Link
                to={ADMIN_ROUTES.assignments}
                className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-medium text-slate-200 transition hover:border-sky-500/60 hover:text-white"
              >
                Coordinate assignments
              </Link>
              <Link
                to={ADMIN_ROUTES.completionReports}
                className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-medium text-slate-200 transition hover:border-sky-500/60 hover:text-white"
              >
                Verify evidence
              </Link>
              <Link
                to={ADMIN_ROUTES.documents}
                className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-medium text-slate-200 transition hover:border-sky-500/60 hover:text-white"
              >
                Manage documents
              </Link>
              <Link
                to={ADMIN_ROUTES.customers}
                className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-medium text-slate-200 transition hover:border-sky-500/60 hover:text-white"
              >
                Look up a customer
              </Link>
            </div>
          </section>
        </>
      )}
    </div>
  )
}
