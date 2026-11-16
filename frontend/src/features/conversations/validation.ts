import type {
  FieldErrors,
  ValidationResult,
} from '../../lib/forms/validation.ts'
import type { MessageCreateRequest } from './types'

export const MESSAGE_CONTENT_MAX_LENGTH = 10000

export interface MessageFormValues {
  content: string
}

export function validateMessageForm(
  values: MessageFormValues,
): ValidationResult<MessageCreateRequest> {
  const errors: FieldErrors = {}
  const content = values.content.trim()

  if (!content) {
    errors.content = 'Write a message before sending.'
  } else if (content.length > MESSAGE_CONTENT_MAX_LENGTH) {
    errors.content = `Messages must be ${MESSAGE_CONTENT_MAX_LENGTH} characters or fewer.`
  }

  if (Object.keys(errors).length > 0) {
    return { isValid: false, errors, payload: null }
  }

  return {
    isValid: true,
    errors,
    payload: { content },
  }
}
