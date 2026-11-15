import type { FieldErrors, ValidationResult } from '../../lib/forms/validation.ts'
import type { ComplaintCreateRequest } from './types'

export interface ComplaintFormValues {
  description: string
  equipmentId: string
  errorCode: string
}

const DESCRIPTION_MIN_LENGTH = 5
const DESCRIPTION_MAX_LENGTH = 10000
const ERROR_CODE_MAX_LENGTH = 100

export function validateComplaintForm(
  values: ComplaintFormValues,
  allowedEquipmentIds: readonly string[],
): ValidationResult<ComplaintCreateRequest> {
  const errors: FieldErrors = {}
  const description = values.description.trim()
  const equipmentId = values.equipmentId.trim()
  const errorCode = values.errorCode.trim()

  if (!description) {
    errors.description = 'Describe the problem before submitting.'
  } else if (description.length < DESCRIPTION_MIN_LENGTH) {
    errors.description = `Description must be at least ${DESCRIPTION_MIN_LENGTH} characters.`
  } else if (description.length > DESCRIPTION_MAX_LENGTH) {
    errors.description = `Description must be ${DESCRIPTION_MAX_LENGTH} characters or fewer.`
  }

  if (equipmentId && !allowedEquipmentIds.includes(equipmentId)) {
    errors.equipmentId = 'Select equipment from your registered equipment.'
  }

  if (errorCode.length > ERROR_CODE_MAX_LENGTH) {
    errors.errorCode = `Error code must be ${ERROR_CODE_MAX_LENGTH} characters or fewer.`
  }

  if (Object.keys(errors).length > 0) {
    return { isValid: false, errors, payload: null }
  }

  return {
    isValid: true,
    errors,
    payload: {
      description,
      equipment_id: equipmentId || null,
      reported_error_code: errorCode || null,
    },
  }
}
