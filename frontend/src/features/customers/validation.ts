import type { FieldErrors, ValidationResult } from '../../lib/forms/validation.ts'
import type { CustomerUpdateRequest } from './types'

export interface CustomerProfileFormValues {
  address: string
  preferredLanguage: string
}

const ADDRESS_MAX_LENGTH = 2000
const LANGUAGE_MIN_LENGTH = 2
const LANGUAGE_MAX_LENGTH = 30

export function validateCustomerProfileForm(
  values: CustomerProfileFormValues,
): ValidationResult<CustomerUpdateRequest> {
  const errors: FieldErrors = {}
  const address = values.address.trim()
  const preferredLanguage = values.preferredLanguage.trim()

  if (address.length > ADDRESS_MAX_LENGTH) {
    errors.address = `Address must be ${ADDRESS_MAX_LENGTH} characters or fewer.`
  }

  if (
    preferredLanguage.length > 0 &&
    preferredLanguage.length < LANGUAGE_MIN_LENGTH
  ) {
    errors.preferredLanguage = `Preferred language must be at least ${LANGUAGE_MIN_LENGTH} characters.`
  }

  if (preferredLanguage.length > LANGUAGE_MAX_LENGTH) {
    errors.preferredLanguage = `Preferred language must be ${LANGUAGE_MAX_LENGTH} characters or fewer.`
  }

  if (Object.keys(errors).length > 0) {
    return { isValid: false, errors, payload: null }
  }

  return {
    isValid: true,
    errors,
    payload: {
      address: address || null,
      preferred_language: preferredLanguage || null,
    },
  }
}
