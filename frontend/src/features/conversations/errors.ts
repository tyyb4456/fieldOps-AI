import {
  apiErrorMessage,
  isApiError,
  isNotFoundError,
} from '../../lib/api/errors.ts'

export function isUnsupportedChannelError(error: unknown): boolean {
  return (
    isApiError(error) &&
    error.code === 'unsupported_conversation_channel'
  )
}

export function isIdempotencyConflictError(error: unknown): boolean {
  return isApiError(error) && error.code === 'idempotency_conflict'
}

export function isUncertainSubmissionError(error: unknown): boolean {
  return (
    isApiError(error) && (error.status === 0 || error.status >= 500)
  )
}

export function conversationListErrorMessage(error: unknown): string {
  if (isNotFoundError(error)) {
    return 'This complaint could not be found or is not available to your account.'
  }

  return apiErrorMessage(
    error,
    'Unable to load conversations for this complaint.',
  )
}

export function messageListErrorMessage(error: unknown): string {
  if (isNotFoundError(error)) {
    return 'This conversation could not be found or is not available to your account.'
  }

  return apiErrorMessage(error, 'Unable to load this conversation.')
}

export function messageSubmissionErrorMessage(error: unknown): string {
  if (isUnsupportedChannelError(error)) {
    return 'Messages can only be sent through web conversations. This conversation is read-only in the application.'
  }

  if (isIdempotencyConflictError(error)) {
    return 'This message could not be sent because its submission key was already used for different content. Review your message and try sending it again.'
  }

  if (isUncertainSubmissionError(error)) {
    return 'We could not confirm whether your message was sent. Your message has been kept so you can safely retry the same submission.'
  }

  return apiErrorMessage(
    error,
    'Unable to send your message. Please try again.',
  )
}
