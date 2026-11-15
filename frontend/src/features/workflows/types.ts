import type {
  WorkflowRunStatus,
  WorkflowRunType,
} from '../../lib/api/types'
import type { DiagnosticInvestigation } from '../diagnostics/types'

export interface WorkflowRun {
  id: string
  complaint_id: string
  workflow_type: WorkflowRunType | null
  status: WorkflowRunStatus
  current_step: string | null
  started_at: string
  finished_at: string | null
  error_message: string | null
}

export interface WorkflowRunAccepted {
  workflow_run_id: string
  complaint_id: string
  workflow_type: WorkflowRunType
  status: WorkflowRunStatus
  current_step: string | null
}

export interface WorkflowRunDetail extends WorkflowRun {
  diagnostic: DiagnosticInvestigation | null
  proposal_id: string | null
}

export interface WorkflowRunListQuery {
  complaint_id?: string
  status?: WorkflowRunStatus
  limit?: number
  offset?: number
}

export interface WorkflowRunCreateRequest {
  current_step?: string | null
}

export interface WorkflowRunStatusUpdateRequest {
  status: WorkflowRunStatus
  current_step?: string | null
  error_message?: string | null
}
