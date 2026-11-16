export const USER_ROLES = ['customer', 'technician', 'admin'] as const
export type UserRole = (typeof USER_ROLES)[number]

export const PRIORITIES = ['normal', 'high', 'urgent'] as const
export type Priority = (typeof PRIORITIES)[number]

export const COMPLAINT_CHANNELS = ['web', 'whatsapp'] as const
export type ComplaintChannel = (typeof COMPLAINT_CHANNELS)[number]

export const MESSAGE_SENDER_TYPES = [
  'customer',
  'assistant',
  'staff',
] as const
export type MessageSenderType = (typeof MESSAGE_SENDER_TYPES)[number]

export const COMPLAINT_STATUSES = [
  'received',
  'analyzing',
  'awaiting_customer',
  'ready_for_work_order',
  'converted',
  'escalated',
  'closed',
  'cancelled',
] as const
export type ComplaintStatus = (typeof COMPLAINT_STATUSES)[number]

export const WORK_ORDER_STATUSES = [
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
export type WorkOrderStatus = (typeof WORK_ORDER_STATUSES)[number]

export const ASSIGNMENT_STATUSES = [
  'offered',
  'accepted',
  'rejected',
  'withdrawn',
  'expired',
] as const
export type AssignmentStatus = (typeof ASSIGNMENT_STATUSES)[number]

export const EVIDENCE_STATUSES = ['pending', 'verified', 'rejected'] as const
export type EvidenceStatus = (typeof EVIDENCE_STATUSES)[number]

export const WORKFLOW_RUN_STATUSES = [
  'running',
  'paused',
  'completed',
  'failed',
] as const
export type WorkflowRunStatus = (typeof WORKFLOW_RUN_STATUSES)[number]

export const WORKFLOW_RUN_TYPES = [
  'diagnostic_investigation',
  'work_order_proposal',
] as const
export type WorkflowRunType = (typeof WORKFLOW_RUN_TYPES)[number]

export const WORK_ORDER_PROPOSAL_STATUSES = [
  'pending_approval',
  'approved',
  'rejected',
] as const
export type WorkOrderProposalStatus =
  (typeof WORK_ORDER_PROPOSAL_STATUSES)[number]

export const INGESTION_STATUSES = [
  'pending',
  'processing',
  'ready',
  'failed',
] as const
export type IngestionStatus = (typeof INGESTION_STATUSES)[number]

export const DIAGNOSTIC_STATUSES = [
  'diagnosed',
  'needs_more_information',
  'insufficient_evidence',
  'conflicting_evidence',
] as const
export type DiagnosticStatus = (typeof DIAGNOSTIC_STATUSES)[number]

export const ANSWER_STATUSES = [
  'answered',
  'insufficient_evidence',
  'conflicting_evidence',
] as const
export type AnswerStatus = (typeof ANSWER_STATUSES)[number]

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

export function isUserRole(value: unknown): value is UserRole {
  return (
    typeof value === 'string' &&
    (USER_ROLES as readonly string[]).includes(value)
  )
}

export function isPriority(value: unknown): value is Priority {
  return (
    typeof value === 'string' &&
    (PRIORITIES as readonly string[]).includes(value)
  )
}

export function isComplaintChannel(value: unknown): value is ComplaintChannel {
  return (
    typeof value === 'string' &&
    (COMPLAINT_CHANNELS as readonly string[]).includes(value)
  )
}

export function isMessageSenderType(
  value: unknown,
): value is MessageSenderType {
  return (
    typeof value === 'string' &&
    (MESSAGE_SENDER_TYPES as readonly string[]).includes(value)
  )
}

export function isComplaintStatus(value: unknown): value is ComplaintStatus {
  return (
    typeof value === 'string' &&
    (COMPLAINT_STATUSES as readonly string[]).includes(value)
  )
}

export function isWorkOrderStatus(value: unknown): value is WorkOrderStatus {
  return (
    typeof value === 'string' &&
    (WORK_ORDER_STATUSES as readonly string[]).includes(value)
  )
}

export function isAssignmentStatus(value: unknown): value is AssignmentStatus {
  return (
    typeof value === 'string' &&
    (ASSIGNMENT_STATUSES as readonly string[]).includes(value)
  )
}

export function isEvidenceStatus(value: unknown): value is EvidenceStatus {
  return (
    typeof value === 'string' &&
    (EVIDENCE_STATUSES as readonly string[]).includes(value)
  )
}

export function isAnswerStatus(value: unknown): value is AnswerStatus {
  return (
    typeof value === 'string' &&
    (ANSWER_STATUSES as readonly string[]).includes(value)
  )
}
