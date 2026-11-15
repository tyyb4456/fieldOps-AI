export type FieldErrors = Record<string, string>

export interface ValidationResult<T> {
  isValid: boolean
  errors: FieldErrors
  payload: T | null
}

export function hasFieldErrors(errors: FieldErrors): boolean {
  return Object.keys(errors).length > 0
}
