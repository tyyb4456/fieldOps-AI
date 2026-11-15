import type { WorkOrderStatus } from '../../lib/api/types'

export type TechnicianWorkOrderPhase =
  | 'awaiting_response'
  | 'ready_to_start'
  | 'in_progress'
  | 'awaiting_parts'
  | 'awaiting_verification'
  | 'escalated'
  | 'terminal'
  | 'unavailable'

export interface TechnicianLifecycleInput {
  workOrderStatus: WorkOrderStatus
  hasOfferedAssignment: boolean
  hasAcceptedAssignment: boolean
  hasServiceRecord: boolean
  hasEligibleServiceRecord: boolean
}

export interface TechnicianLifecycle {
  phase: TechnicianWorkOrderPhase
  canAccept: boolean
  canReject: boolean
  canStartWork: boolean
  canMarkAwaitingParts: boolean
  canSubmitForVerification: boolean
  canEscalate: boolean
  canResumeWork: boolean
  canCreateServiceRecord: boolean
  canUpdateServiceRecords: boolean
  canCreateCompletionReport: boolean
  message: string
}

export type WorkOrderPhaseGroup =
  | 'awaiting_response'
  | 'accepted'
  | 'in_progress'
  | 'paused_or_escalated'
  | 'awaiting_verification'
  | 'terminal'
  | 'other'

const ACTIVE_SERVICE_STATUSES = new Set<WorkOrderStatus>([
  'accepted',
  'in_progress',
  'awaiting_parts',
])

const COMPLETION_REPORT_STATUSES = new Set<WorkOrderStatus>([
  'accepted',
  'in_progress',
  'awaiting_parts',
  'pending_verification',
])

export function canModifyServiceRecords(
  status: WorkOrderStatus,
): boolean {
  return ACTIVE_SERVICE_STATUSES.has(status)
}

export function canModifyCompletionReports(
  status: WorkOrderStatus,
): boolean {
  return COMPLETION_REPORT_STATUSES.has(status)
}

export function workOrderPhaseGroup(
  status: WorkOrderStatus,
): WorkOrderPhaseGroup {
  switch (status) {
    case 'assigned':
      return 'awaiting_response'
    case 'accepted':
      return 'accepted'
    case 'in_progress':
      return 'in_progress'
    case 'awaiting_parts':
    case 'escalated':
      return 'paused_or_escalated'
    case 'pending_verification':
      return 'awaiting_verification'
    case 'completed':
    case 'cancelled':
      return 'terminal'
    default:
      return 'other'
  }
}

export function getTechnicianLifecycle({
  workOrderStatus,
  hasOfferedAssignment,
  hasAcceptedAssignment,
  hasServiceRecord,
  hasEligibleServiceRecord,
}: TechnicianLifecycleInput): TechnicianLifecycle {
  if (hasOfferedAssignment && workOrderStatus === 'assigned') {
    return {
      phase: 'awaiting_response',
      canAccept: true,
      canReject: true,
      canStartWork: false,
      canMarkAwaitingParts: false,
      canSubmitForVerification: false,
      canEscalate: false,
      canResumeWork: false,
      canCreateServiceRecord: false,
      canUpdateServiceRecords: false,
      canCreateCompletionReport: false,
      message: 'Review this offer and accept it before starting work.',
    }
  }

  if (!hasAcceptedAssignment) {
    return {
      phase: 'unavailable',
      canAccept: false,
      canReject: false,
      canStartWork: false,
      canMarkAwaitingParts: false,
      canSubmitForVerification: false,
      canEscalate: false,
      canResumeWork: false,
      canCreateServiceRecord: false,
      canUpdateServiceRecords: false,
      canCreateCompletionReport: false,
      message: 'An accepted assignment is required for technician actions.',
    }
  }

  const canUseServiceRecords = ACTIVE_SERVICE_STATUSES.has(workOrderStatus)
  const canCreateCompletionReport =
    COMPLETION_REPORT_STATUSES.has(workOrderStatus) &&
    hasEligibleServiceRecord

  switch (workOrderStatus) {
    case 'accepted':
      return {
        phase: 'ready_to_start',
        canAccept: false,
        canReject: false,
        canStartWork: true,
        canMarkAwaitingParts: false,
        canSubmitForVerification: false,
        canEscalate: false,
        canResumeWork: false,
        canCreateServiceRecord: canUseServiceRecords,
        canUpdateServiceRecords: canUseServiceRecords,
        canCreateCompletionReport,
        message: 'Start work when you are ready, then record service activity.',
      }
    case 'in_progress':
      return {
        phase: 'in_progress',
        canAccept: false,
        canReject: false,
        canStartWork: false,
        canMarkAwaitingParts: true,
        canSubmitForVerification: hasServiceRecord,
        canEscalate: true,
        canResumeWork: false,
        canCreateServiceRecord: canUseServiceRecords,
        canUpdateServiceRecords: canUseServiceRecords,
        canCreateCompletionReport,
        message:
          'Record service activity and submit for verification when the job is complete.',
      }
    case 'awaiting_parts':
      return {
        phase: 'awaiting_parts',
        canAccept: false,
        canReject: false,
        canStartWork: false,
        canMarkAwaitingParts: false,
        canSubmitForVerification: false,
        canEscalate: false,
        canResumeWork: true,
        canCreateServiceRecord: canUseServiceRecords,
        canUpdateServiceRecords: canUseServiceRecords,
        canCreateCompletionReport,
        message: 'Resume work once the required parts are available.',
      }
    case 'pending_verification':
      return {
        phase: 'awaiting_verification',
        canAccept: false,
        canReject: false,
        canStartWork: false,
        canMarkAwaitingParts: false,
        canSubmitForVerification: false,
        canEscalate: false,
        canResumeWork: false,
        canCreateServiceRecord: false,
        canUpdateServiceRecords: false,
        canCreateCompletionReport,
        message: 'The service team is verifying the completion evidence.',
      }
    case 'escalated':
      return {
        phase: 'escalated',
        canAccept: false,
        canReject: false,
        canStartWork: false,
        canMarkAwaitingParts: false,
        canSubmitForVerification: false,
        canEscalate: false,
        canResumeWork: false,
        canCreateServiceRecord: false,
        canUpdateServiceRecords: false,
        canCreateCompletionReport: false,
        message: 'This work order was escalated to the service team.',
      }
    case 'completed':
    case 'cancelled':
      return {
        phase: 'terminal',
        canAccept: false,
        canReject: false,
        canStartWork: false,
        canMarkAwaitingParts: false,
        canSubmitForVerification: false,
        canEscalate: false,
        canResumeWork: false,
        canCreateServiceRecord: false,
        canUpdateServiceRecords: false,
        canCreateCompletionReport: false,
        message: 'This work order is closed.',
      }
    default:
      return {
        phase: 'unavailable',
        canAccept: false,
        canReject: false,
        canStartWork: false,
        canMarkAwaitingParts: false,
        canSubmitForVerification: false,
        canEscalate: false,
        canResumeWork: false,
        canCreateServiceRecord: false,
        canUpdateServiceRecords: false,
        canCreateCompletionReport: false,
        message: 'This work order is not ready for technician action.',
      }
  }
}
