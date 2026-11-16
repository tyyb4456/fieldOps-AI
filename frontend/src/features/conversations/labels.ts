import type {
  ComplaintChannel,
  MessageSenderType,
} from '../../lib/api/types'
import { CHANNEL_LABELS } from '../complaints/labels'

export const SENDER_LABELS: Record<MessageSenderType, string> = {
  customer: 'You',
  staff: 'Service team',
  assistant: 'FieldOps assistant',
}

export function conversationChannelLabel(
  channel: ComplaintChannel,
): string {
  return CHANNEL_LABELS[channel]
}
