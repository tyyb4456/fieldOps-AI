import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { EmptyState } from '../../../components/EmptyState'
import { ErrorScreen } from '../../../components/ErrorScreen'
import { FormField, inputClassName } from '../../../components/FormField'
import { LoadingScreen } from '../../../components/LoadingScreen'
import { PageHeader } from '../../../components/PageHeader'
import { useApiClient } from '../../../lib/api/api-client-context'
import type { WorkflowRunStatus } from '../../../lib/api/types'
import { formatDateTime } from '../../../lib/format'
import { useAsyncData } from '../../../lib/hooks/use-async-data'
import { listAdminWorkflowRuns } from '../api'
import { AdminPagination } from '../components/AdminPagination'
import { WorkflowStatusBadge } from '../components/AdminBadges'
import {
  adminWorkflowErrorMessage,
} from '../errors'
import {
  WORKFLOW_STATUS_LABELS,
  workflowTypeLabel,
} from '../labels'
import { ADMIN_ROUTES, adminWorkflowPath } from '../routes'

const PAGE_SIZE = 20

export function AdminWorkflowsPage() {
  const apiClient = useApiClient()
  const [offset, setOffset] = useState(0)
  const [status, setStatus] = useState<WorkflowRunStatus | ''>('')
  const [complaintInput, setComplaintInput] = useState('')
  const [complaintId, setComplaintId] = useState('')

  const { data, error, isLoading, reload } = useAsyncData(
    (signal) =>
      listAdminWorkflowRuns(
        apiClient,
        {
          status: status || undefined,
          complaint_id: complaintId || undefined,
          limit: PAGE_SIZE,
          offset,
        },
        signal,
      ),
    [apiClient, offset, status, complaintId],
  )

  function applyComplaintFilter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setOffset(0)
    setComplaintId(complaintInput.trim())
  }

  return (
    <div className="grid gap-6">
      <PageHeader
        eyebrow="Administrator"
        title="Workflow runs"
        description="Monitor asynchronous diagnostic and proposal workflows, including running and failed runs."
      />

      <section className="grid gap-4 rounded-2xl border border-slate-800 bg-slate-900/60 p-5 sm:grid-cols-2">
        <FormField id="admin-workflow-status-filter" label="Status">
          <select
            id="admin-workflow-status-filter"
            className={inputClassName}
            value={status}
            onChange={(event) => {
              setOffset(0)
              setStatus(event.target.value as WorkflowRunStatus | '')
            }}
          >
            <option value="">All statuses</option>
            {(
              Object.keys(WORKFLOW_STATUS_LABELS) as WorkflowRunStatus[]
            ).map((value) => (
              <option key={value} value={value}>
                {WORKFLOW_STATUS_LABELS[value]}
              </option>
            ))}
          </select>
        </FormField>
        <form onSubmit={applyComplaintFilter} className="grid gap-2">
          <FormField
            id="admin-workflow-complaint-filter"
            label="Complaint ID"
            hint="Filter by the exact complaint identifier."
          >
            <div className="flex gap-2">
              <input
                id="admin-workflow-complaint-filter"
                className={inputClassName}
                value={complaintInput}
                onChange={(event) => setComplaintInput(event.target.value)}
                placeholder="00000000-0000-0000-0000-000000000000"
              />
              <button
                type="submit"
                className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-medium text-slate-200 transition hover:border-slate-500"
              >
                Apply
              </button>
            </div>
          </FormField>
        </form>
      </section>

      {isLoading ? (
        <LoadingScreen label="Loading workflow runs..." />
      ) : error || !data ? (
        <ErrorScreen
          message={adminWorkflowErrorMessage(error)}
          onRetry={reload}
        />
      ) : data.items.length === 0 ? (
        <EmptyState
          title="No workflow runs match these filters"
          description="Generate a proposal from a ready complaint to start a workflow run."
        />
      ) : (
        <>
          <ul className="grid gap-3">
            {data.items.map((run) => (
              <li key={run.id}>
                <Link
                  to={adminWorkflowPath(run.id)}
                  className="block rounded-2xl border border-slate-800 bg-slate-900/60 p-5 transition hover:border-sky-500/40"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <WorkflowStatusBadge status={run.status} />
                    <span className="text-xs text-slate-500">
                      {workflowTypeLabel(run.workflow_type)}
                    </span>
                    <span className="text-xs text-slate-500">
                      Started {formatDateTime(run.started_at)}
                    </span>
                  </div>
                  <p className="mt-3 font-mono text-xs text-slate-500">
                    Complaint {run.complaint_id}
                  </p>
                  {run.current_step ? (
                    <p className="mt-1 text-sm text-slate-300">
                      Current step: {run.current_step}
                    </p>
                  ) : null}
                  {run.error_message ? (
                    <p className="mt-2 text-xs text-rose-300">
                      {run.error_message}
                    </p>
                  ) : null}
                </Link>
              </li>
            ))}
          </ul>
          <AdminPagination
            offset={offset}
            pageSize={PAGE_SIZE}
            total={data.total}
            noun="workflow runs"
            onOffsetChange={setOffset}
          />
        </>
      )}

      <Link
        to={ADMIN_ROUTES.dashboard}
        className="w-fit rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-medium text-slate-200 transition hover:border-slate-500"
      >
        Back to dashboard
      </Link>
    </div>
  )
}
