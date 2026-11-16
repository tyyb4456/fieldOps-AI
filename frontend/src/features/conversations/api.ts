import type { ApiClient } from '../../lib/api/client.ts'
import { ApiError } from '../../lib/api/errors.ts'
import {
  isRecord,
  parsePaginatedResponse,
  requireString,
} from '../../lib/api/parse.ts'
import {
  isComplaintChannel,
  isMessageSenderType,
} from '../../lib/api/types.ts'
import type {
  Conversation,
  ConversationListQuery,
  ConversationListResponse,
  Message,
  MessageListQuery,
  MessageListResponse,
} from './types'

function invalidConversationResponse(): ApiError {
  return new ApiError(
    500,
    'invalid_response',
    'The API returned an invalid conversation response.',
  )
}

function invalidMessageResponse(): ApiError {
  return new ApiError(
    500,
    'invalid_response',
    'The API returned an invalid message response.',
  )
}

export function parseConversation(payload: unknown): Conversation {
  if (!isRecord(payload)) {
    throw invalidConversationResponse()
  }

  if (!isComplaintChannel(payload.channel)) {
    throw new ApiError(
      500,
      'invalid_response',
      'The API returned an invalid conversation channel.',
    )
  }

  return {
    id: requireString(payload.id, 'id'),
    complaint_id: requireString(payload.complaint_id, 'complaint_id'),
    channel: payload.channel,
    created_at: requireString(payload.created_at, 'created_at'),
  }
}

export function parseMessage(payload: unknown): Message {
  if (!isRecord(payload)) {
    throw invalidMessageResponse()
  }

  if (!isMessageSenderType(payload.sender_type)) {
    throw new ApiError(
      500,
      'invalid_response',
      'The API returned an invalid message sender type.',
    )
  }

  return {
    id: requireString(payload.id, 'id'),
    conversation_id: requireString(
      payload.conversation_id,
      'conversation_id',
    ),
    sender_type: payload.sender_type,
    content: requireString(payload.content, 'content'),
    created_at: requireString(payload.created_at, 'created_at'),
  }
}

export async function listComplaintConversations(
  client: ApiClient,
  complaintId: string,
  query: ConversationListQuery = {},
  signal?: AbortSignal,
): Promise<ConversationListResponse> {
  const payload = await client.get<unknown>(
    `/api/v1/customers/me/complaints/${encodeURIComponent(complaintId)}/conversations`,
    {
      query: { limit: query.limit, offset: query.offset },
      signal,
    },
  )
  return parsePaginatedResponse(payload, parseConversation, 'conversation')
}

export async function listConversationMessages(
  client: ApiClient,
  conversationId: string,
  query: MessageListQuery = {},
  signal?: AbortSignal,
): Promise<MessageListResponse> {
  const payload = await client.get<unknown>(
    `/api/v1/customers/me/conversations/${encodeURIComponent(conversationId)}/messages`,
    {
      query: { limit: query.limit, offset: query.offset },
      signal,
    },
  )
  return parsePaginatedResponse(payload, parseMessage, 'message')
}

export async function sendConversationMessage(
  client: ApiClient,
  conversationId: string,
  content: string,
  idempotencyKey: string,
  signal?: AbortSignal,
): Promise<Message> {
  const payload = await client.post<unknown>(
    `/api/v1/customers/me/conversations/${encodeURIComponent(conversationId)}/messages`,
    {
      json: { content },
      headers: { 'Idempotency-Key': idempotencyKey },
      signal,
    },
  )
  return parseMessage(payload)
}
