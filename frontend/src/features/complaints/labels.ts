import type { BadgeTone } from '../../components/Badge'
import type {
  ComplaintChannel,
  ComplaintStatus,
  Priority,
} from '../../lib/api/types'

export const COMPLAINT_STATUS_LABELS: Record<ComplaintStatus, string> = {
  received: 'Received',
  analyzing: 'Analyzing',
  awaiting_customer: 'Awaiting your response',
  ready_for_work_order: 'Ready for work order',
  converted: 'Work order created',
  escalated: 'Escalated',
  closed: 'Closed',
  cancelled: 'Cancelled',
}

const STATUS_TONES: Record<ComplaintStatus, BadgeTone> = {
  received: 'info',
  analyzing: 'info',
  awaiting_customer: 'warning',
  ready_for_work_order: 'success',
  converted: 'success',
  escalated: 'danger',
  closed: 'neutral',
  cancelled: 'neutral',
}

export const PRIORITY_LABELS: Record<Priority, string> = {
  normal: 'Normal',
  high: 'High',
  urgent: 'Urgent',
}

const PRIORITY_TONES: Record<Priority, BadgeTone> = {
  normal: 'neutral',
  high: 'warning',
  urgent: 'danger',
}

export const CHANNEL_LABELS: Record<ComplaintChannel, string> = {
  web: 'Web',
  whatsapp: 'WhatsApp',
}

export function complaintStatusLabel(status: ComplaintStatus): string {
  return COMPLAINT_STATUS_LABELS[status]
}

export function complaintStatusTone(status: ComplaintStatus): BadgeTone {
  return STATUS_TONES[status]
}

export function priorityLabel(priority: Priority): string {
  return PRIORITY_LABELS[priority]
}

export function priorityTone(priority: Priority): BadgeTone {
  return PRIORITY_TONES[priority]
}
