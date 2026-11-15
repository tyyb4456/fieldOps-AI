import { apiErrorMessage, isApiError } from '../../lib/api/errors.ts'

export function adminProposalErrorMessage(error: unknown): string {
  if (isApiError(error)) {
    switch (error.code) {
      case 'complaint_not_eligible':
        return 'This complaint is not eligible for work-order preparation. It must be ready for a work order and have linked equipment.'
      case 'proposal_already_pending':
        return 'A work-order proposal is already pending review for this complaint.'
      case 'proposal_conflict':
        return 'A work order or proposal already exists for this complaint.'
      case 'invalid_proposal_state':
        return 'This proposal can no longer be changed in its current state.'
      case 'proposal_stale':
        return 'This proposal is stale. Generate a new proposal before deciding.'
      case 'technician_not_eligible':
        return 'The selected technician is no longer eligible for this proposal.'
      case 'not_found':
        return 'This work-order proposal could not be found.'
    }
  }

  return apiErrorMessage(error, 'Unable to update this work-order proposal.')
}

export function adminWorkOrderErrorMessage(error: unknown): string {
  if (isApiError(error)) {
    switch (error.code) {
      case 'invalid_status_transition':
        return 'The work order cannot be moved to that state right now.'
      case 'work_order_not_editable':
        return 'Work-order fields can only be changed while the work order is draft, validated, or awaiting assignment.'
      case 'work_order_conflict':
        return 'A work order already exists for this complaint.'
      case 'invalid_complaint_state':
        return 'The complaint is not eligible for work-order conversion.'
      case 'not_found':
        return 'This work order could not be found.'
    }
  }

  return apiErrorMessage(error, 'Unable to update this work order.')
}

export function adminAssignmentErrorMessage(error: unknown): string {
  if (isApiError(error)) {
    switch (error.code) {
      case 'assignment_conflict':
        return 'This work order already has an active assignment.'
      case 'invalid_assignment_state':
        return 'The assignment cannot be changed in its current state.'
      case 'technician_not_eligible':
        return 'The selected technician is not eligible for assignment.'
      case 'not_found':
        return 'This assignment could not be found.'
    }
  }

  return apiErrorMessage(error, 'Unable to update this assignment.')
}

export function adminCompletionReportErrorMessage(error: unknown): string {
  if (isApiError(error)) {
    switch (error.code) {
      case 'invalid_completion_report_state':
        return 'This completion report cannot be changed in its current state. Verified reports are immutable.'
      case 'completion_report_conflict':
        return 'A completion report already exists for this work order.'
      case 'forbidden':
        return 'You do not have permission to change completion verification fields.'
      case 'not_found':
        return 'This completion report could not be found.'
    }
  }

  return apiErrorMessage(error, 'Unable to update this completion report.')
}

export function adminDocumentErrorMessage(error: unknown): string {
  if (isApiError(error)) {
    switch (error.code) {
      case 'document_conflict':
        return 'A document with this identity already exists.'
      case 'document_in_use':
        return 'This document cannot be deleted in its current state.'
      case 'document_too_large':
        return 'The uploaded file is larger than the allowed maximum.'
      case 'document_storage_unavailable':
        return 'Document storage is unavailable. Try again shortly.'
      case 'document_not_ready':
        return 'The document must finish ingestion with at least one chunk before it can be activated.'
      case 'document_integrity_failed':
        return 'The stored document does not match its recorded integrity metadata.'
      case 'ingestion_in_progress':
        return 'Document ingestion is already in progress.'
      case 'invalid_document':
        return 'Document metadata is invalid. Check the required fields.'
      case 'not_found':
        return 'This document could not be found.'
    }
  }

  return apiErrorMessage(error, 'Unable to update this document.')
}

export function adminEquipmentErrorMessage(error: unknown): string {
  if (isApiError(error)) {
    switch (error.code) {
      case 'equipment_conflict':
        return 'Equipment conflicts with an existing record.'
      case 'equipment_in_use':
        return 'Equipment has historical records and cannot be deleted.'
      case 'not_found':
        return 'This equipment could not be found.'
    }
  }

  return apiErrorMessage(error, 'Unable to update this equipment.')
}

export function adminCustomerLookupErrorMessage(error: unknown): string {
  if (isApiError(error) && error.code === 'not_found') {
    return 'No customer matches that identifier.'
  }

  return apiErrorMessage(error, 'Unable to load this customer profile.')
}

export function adminComplaintDetailErrorMessage(error: unknown): string {
  if (isApiError(error) && error.code === 'not_found') {
    return 'This complaint could not be found.'
  }

  return apiErrorMessage(error, 'Unable to load this complaint.')
}

export function adminWorkflowErrorMessage(error: unknown): string {
  if (isApiError(error) && error.code === 'not_found') {
    return 'This workflow run could not be found.'
  }

  return apiErrorMessage(error, 'Unable to load workflow runs.')
}

export function adminTechnicianErrorMessage(error: unknown): string {
  return apiErrorMessage(error, 'Unable to load eligible technicians.')
}
