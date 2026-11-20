import type { BadgeTone } from '../../components/Badge'
import type {
  DiagnosticStatus,
  IngestionStatus,
  WorkOrderProposalStatus,
  WorkflowRunStatus,
  WorkflowRunType,
} from '../../lib/api/types'

export const PROPOSAL_STATUS_LABELS: Record<WorkOrderProposalStatus, string> = {
  pending_approval: 'Pending approval',
  approved: 'Approved',
  rejected: 'Rejected',
  superseded: 'Superseded',
}

const PROPOSAL_STATUS_TONES: Record<WorkOrderProposalStatus, BadgeTone> = {
  pending_approval: 'warning',
  approved: 'success',
  rejected: 'neutral',
  superseded: 'neutral',
}

export const WORKFLOW_STATUS_LABELS: Record<WorkflowRunStatus, string> = {
  running: 'Running',
  paused: 'Paused',
  completed: 'Completed',
  failed: 'Failed',
}

const WORKFLOW_STATUS_TONES: Record<WorkflowRunStatus, BadgeTone> = {
  running: 'info',
  paused: 'warning',
  completed: 'success',
  failed: 'danger',
}

export const WORKFLOW_TYPE_LABELS: Record<WorkflowRunType, string> = {
  diagnostic_investigation: 'Diagnostic investigation',
  work_order_proposal: 'Work-order proposal',
}

export const INGESTION_STATUS_LABELS: Record<IngestionStatus, string> = {
  pending: 'Pending',
  processing: 'Processing',
  ready: 'Ready',
  failed: 'Failed',
}

const INGESTION_STATUS_TONES: Record<IngestionStatus, BadgeTone> = {
  pending: 'warning',
  processing: 'info',
  ready: 'success',
  failed: 'danger',
}

export const DIAGNOSTIC_STATUS_LABELS: Record<DiagnosticStatus, string> = {
  diagnosed: 'Diagnosed',
  needs_more_information: 'Needs more information',
  insufficient_evidence: 'Insufficient evidence',
  conflicting_evidence: 'Conflicting evidence',
}

const DIAGNOSTIC_STATUS_TONES: Record<DiagnosticStatus, BadgeTone> = {
  diagnosed: 'success',
  needs_more_information: 'warning',
  insufficient_evidence: 'warning',
  conflicting_evidence: 'danger',
}

export function proposalStatusLabel(
  status: WorkOrderProposalStatus,
): string {
  return PROPOSAL_STATUS_LABELS[status]
}

export function proposalStatusTone(
  status: WorkOrderProposalStatus,
): BadgeTone {
  return PROPOSAL_STATUS_TONES[status]
}

export function workflowStatusLabel(status: WorkflowRunStatus): string {
  return WORKFLOW_STATUS_LABELS[status]
}

export function workflowStatusTone(status: WorkflowRunStatus): BadgeTone {
  return WORKFLOW_STATUS_TONES[status]
}

export function workflowTypeLabel(
  type: WorkflowRunType | null,
): string {
  return type === null ? 'Workflow' : WORKFLOW_TYPE_LABELS[type]
}

export function ingestionStatusLabel(status: IngestionStatus): string {
  return INGESTION_STATUS_LABELS[status]
}

export function ingestionStatusTone(status: IngestionStatus): BadgeTone {
  return INGESTION_STATUS_TONES[status]
}

export function diagnosticStatusLabel(status: DiagnosticStatus): string {
  return DIAGNOSTIC_STATUS_LABELS[status]
}

export function diagnosticStatusTone(status: DiagnosticStatus): BadgeTone {
  return DIAGNOSTIC_STATUS_TONES[status]
}

export const ADMIN_WORK_ORDER_STATUSES = [
  'draft',
  'validated',
  'awaiting_assignment',
  'assigned',
  'accepted',
  'in_progress',
  'awaiting_parts',
  'pending_verification',
  'completed',
  'cancelled',
  'escalated',
] as const

export const ADMIN_COMPLAINT_STATUS_FILTERS = [
  'received',
  'analyzing',
  'awaiting_customer',
  'ready_for_work_order',
  'converted',
  'escalated',
  'closed',
  'cancelled',
] as const
