import { Link, useParams } from 'react-router-dom'
import { ErrorScreen } from '../../../components/ErrorScreen'
import { LoadingScreen } from '../../../components/LoadingScreen'
import { PageHeader } from '../../../components/PageHeader'
import { useApiClient } from '../../../lib/api/api-client-context'
import { formatDateTime } from '../../../lib/format'
import { useAsyncData } from '../../../lib/hooks/use-async-data'
import { getAdminWorkflowRun } from '../api'
import { WorkflowStatusBadge } from '../components/AdminBadges'
import { adminWorkflowErrorMessage } from '../errors'
import { workflowTypeLabel } from '../labels'
import { ADMIN_ROUTES, adminComplaintPath } from '../routes'

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

export function AdminWorkflowDetailPage() {
  const apiClient = useApiClient()
  const { workflowId = '' } = useParams()
  const { data: run, error, isLoading, reload } = useAsyncData(
    (signal) => getAdminWorkflowRun(apiClient, workflowId, signal),
    [apiClient, workflowId],
  )

  if (isLoading) {
    return <LoadingScreen label="Loading workflow run..." />
  }

  if (error || !run) {
    return (
      <ErrorScreen
        message={adminWorkflowErrorMessage(error)}
        onRetry={reload}
      />
    )
  }

  return (
    <div className="grid gap-6">
      <PageHeader
        eyebrow="Workflow run"
        title={workflowTypeLabel(run.workflow_type)}
        description={`Started ${formatDateTime(run.started_at)}`}
        actions={
          <Link
            to={ADMIN_ROUTES.workflows}
            className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-semibold text-slate-200 transition hover:border-slate-500 hover:text-white"
          >
            Back to workflow runs
          </Link>
        }
      />

      <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <div className="flex flex-wrap items-center gap-2">
          <WorkflowStatusBadge status={run.status} />
          <span className="text-xs text-slate-500">
            {run.current_step
              ? `Current step: ${run.current_step}`
              : 'No current step'}
          </span>
        </div>
        {run.error_message ? (
          <p className="mt-3 rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-200">
            {run.error_message}
          </p>
        ) : null}
        <div className="mt-4">
          <Link
            to={adminComplaintPath(run.complaint_id)}
            className="text-sm font-medium text-sky-300 hover:text-sky-200"
          >
            View related complaint
          </Link>
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <DetailRow label="Workflow run ID" value={run.id} />
        <DetailRow label="Complaint ID" value={run.complaint_id} />
        <DetailRow
          label="Workflow type"
          value={workflowTypeLabel(run.workflow_type)}
        />
        <DetailRow label="Started" value={formatDateTime(run.started_at)} />
        <DetailRow
          label="Finished"
          value={run.finished_at ? formatDateTime(run.finished_at) : 'Not finished'}
        />
        <DetailRow label="Current step" value={run.current_step ?? 'None'} />
      </section>

      <p className="text-xs leading-5 text-slate-500">
        Workflow runs are started by the API when a diagnostic investigation or
        proposal is requested. This view is read-only; failed runs require
        investigation before retrying the underlying action.
      </p>
    </div>
  )
}
