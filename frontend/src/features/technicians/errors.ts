import {
  apiErrorMessage,
  isApiError,
  isNotFoundError,
} from '../../lib/api/errors.ts'

export function assignmentActionErrorMessage(error: unknown): string {
  if (isApiError(error)) {
    switch (error.code) {
      case 'invalid_assignment_state':
        return 'This assignment can no longer be changed. It may have been accepted, rejected, or withdrawn.'
      case 'assignment_conflict':
        return 'This work order already has an active assignment.'
      case 'not_found':
        return 'This assignment could not be found or is not available to your account.'
    }
  }

  if (isNotFoundError(error)) {
    return 'This assignment could not be found or is not available to your account.'
  }

  return apiErrorMessage(error, 'Unable to update this assignment.')
}

export function workOrderDetailErrorMessage(error: unknown): string {
  if (isNotFoundError(error)) {
    return 'This work order could not be found or is not available to your account.'
  }

  return apiErrorMessage(error, 'Unable to load this work order.')
}

export function workOrderStatusErrorMessage(error: unknown): string {
  if (isApiError(error) && error.code === 'invalid_status_transition') {
    return 'The work order cannot be moved to that state right now.'
  }

  return apiErrorMessage(error, 'Unable to update the work-order status.')
}

export function serviceRecordErrorMessage(error: unknown): string {
  if (isApiError(error)) {
    switch (error.code) {
      case 'assignment_required':
        return 'An accepted assignment is required before recording service activity.'
      case 'invalid_service_record_state':
        return 'This service record can no longer be changed.'
      case 'service_record_conflict':
        return 'The service record conflicts with the work order or equipment.'
      case 'not_found':
        return 'This service record could not be found or is not available to your account.'
    }
  }

  if (isNotFoundError(error)) {
    return 'This service record could not be found or is not available to your account.'
  }

  return apiErrorMessage(error, 'Unable to save this service record.')
}

export function completionReportErrorMessage(error: unknown): string {
  if (isApiError(error)) {
    switch (error.code) {
      case 'completion_report_conflict':
        return 'A completion report already exists for this work order.'
      case 'invalid_completion_report_association':
        return 'The selected service record does not belong to this work order.'
      case 'invalid_completion_report_state':
        return 'This completion report cannot be changed in its current state.'
      case 'forbidden':
        return 'Only administrators can change completion verification fields.'
      case 'not_found':
        return 'This completion report could not be found or is not available to your account.'
    }
  }

  if (isNotFoundError(error)) {
    return 'This completion report could not be found or is not available to your account.'
  }

  return apiErrorMessage(error, 'Unable to save this completion report.')
}

export function knowledgeErrorMessage(error: unknown): string {
  return apiErrorMessage(error, 'Unable to search the technical knowledge base.')
}
