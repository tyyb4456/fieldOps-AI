import {
  apiErrorMessage,
  isNotFoundError,
} from '../../lib/api/errors.ts'

export function complaintDetailErrorMessage(error: unknown): string {
  if (isNotFoundError(error)) {
    return 'This complaint could not be found or is not available to your account.'
  }

  return apiErrorMessage(error, 'Unable to load this complaint record.')
}
