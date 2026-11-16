import type {
  ComplaintChannel,
  MessageSenderType,
  PaginatedResponse,
} from '../../lib/api/types'

export interface Conversation {
  id: string
  complaint_id: string
  channel: ComplaintChannel
  created_at: string
}

export interface ConversationListQuery {
  limit?: number
  offset?: number
}

export type ConversationListResponse = PaginatedResponse<Conversation>

export interface Message {
  id: string
  conversation_id: string
  sender_type: MessageSenderType
  content: string
  created_at: string
}

export interface MessageListQuery {
  limit?: number
  offset?: number
}

export type MessageListResponse = PaginatedResponse<Message>

export interface MessageCreateRequest {
  content: string
}
