import type { BadgeTone } from '../../components/Badge'
import type {
  AnswerStatus,
  AssignmentStatus,
  EvidenceStatus,
  WorkOrderStatus,
} from '../../lib/api/types'

export const TECHNICIAN_FILTERABLE_WORK_ORDER_STATUSES: readonly WorkOrderStatus[] =
  [
    'assigned',
    'accepted',
    'in_progress',
    'awaiting_parts',
    'pending_verification',
    'escalated',
    'completed',
    'cancelled',
  ]

export const WORK_ORDER_STATUS_LABELS: Record<WorkOrderStatus, string> = {
  draft: 'Draft',
  validated: 'Validated',
  awaiting_assignment: 'Awaiting assignment',
  assigned: 'Awaiting your response',
  accepted: 'Accepted',
  in_progress: 'In progress',
  awaiting_parts: 'Awaiting parts',
  pending_verification: 'Awaiting verification',
  completed: 'Completed',
  cancelled: 'Cancelled',
  escalated: 'Escalated',
}

const WORK_ORDER_STATUS_TONES: Record<WorkOrderStatus, BadgeTone> = {
  draft: 'neutral',
  validated: 'info',
  awaiting_assignment: 'warning',
  assigned: 'warning',
  accepted: 'info',
  in_progress: 'info',
  awaiting_parts: 'warning',
  pending_verification: 'warning',
  completed: 'success',
  cancelled: 'neutral',
  escalated: 'danger',
}

export const ASSIGNMENT_STATUS_LABELS: Record<AssignmentStatus, string> = {
  offered: 'Offered',
  accepted: 'Accepted',
  rejected: 'Rejected',
  withdrawn: 'Withdrawn',
  expired: 'Expired',
}

const ASSIGNMENT_STATUS_TONES: Record<AssignmentStatus, BadgeTone> = {
  offered: 'warning',
  accepted: 'success',
  rejected: 'neutral',
  withdrawn: 'neutral',
  expired: 'neutral',
}

export const EVIDENCE_STATUS_LABELS: Record<EvidenceStatus, string> = {
  pending: 'Pending verification',
  verified: 'Verified',
  rejected: 'Rejected',
}

const EVIDENCE_STATUS_TONES: Record<EvidenceStatus, BadgeTone> = {
  pending: 'warning',
  verified: 'success',
  rejected: 'danger',
}

export const ANSWER_STATUS_LABELS: Record<AnswerStatus, string> = {
  answered: 'Answered',
  insufficient_evidence: 'Insufficient evidence',
  conflicting_evidence: 'Conflicting evidence',
}

const ANSWER_STATUS_TONES: Record<AnswerStatus, BadgeTone> = {
  answered: 'success',
  insufficient_evidence: 'warning',
  conflicting_evidence: 'danger',
}

export function answerStatusLabel(status: AnswerStatus): string {
  return ANSWER_STATUS_LABELS[status]
}

export function answerStatusTone(status: AnswerStatus): BadgeTone {
  return ANSWER_STATUS_TONES[status]
}

export function workOrderStatusLabel(status: WorkOrderStatus): string {
  return WORK_ORDER_STATUS_LABELS[status]
}

export function workOrderStatusTone(status: WorkOrderStatus): BadgeTone {
  return WORK_ORDER_STATUS_TONES[status]
}

export function assignmentStatusLabel(status: AssignmentStatus): string {
  return ASSIGNMENT_STATUS_LABELS[status]
}

export function assignmentStatusTone(status: AssignmentStatus): BadgeTone {
  return ASSIGNMENT_STATUS_TONES[status]
}

export function evidenceStatusLabel(status: EvidenceStatus): string {
  return EVIDENCE_STATUS_LABELS[status]
}

export function evidenceStatusTone(status: EvidenceStatus): BadgeTone {
  return EVIDENCE_STATUS_TONES[status]
}
