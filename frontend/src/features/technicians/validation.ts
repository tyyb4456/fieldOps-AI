import type { FieldErrors, ValidationResult } from '../../lib/forms/validation.ts'
import type {
  CompletionReportCreateRequest,
  CompletionReportUpdateRequest,
  ServiceRecordCreateRequest,
} from '../work-orders/types'

const TEXT_MAX_LENGTH = 10000

export interface ServiceRecordFormValues {
  findings: string
  workPerformed: string
  partsUsed: string
}

export const EMPTY_SERVICE_RECORD_FORM: ServiceRecordFormValues = {
  findings: '',
  workPerformed: '',
  partsUsed: '',
}

export function parsePartsUsed(value: string): string[] {
  return value
    .split('\n')
    .map((part) => part.trim())
    .filter((part) => part.length > 0)
}

export function validateServiceRecordForm(
  values: ServiceRecordFormValues,
): ValidationResult<ServiceRecordCreateRequest> {
  const errors: FieldErrors = {}
  const findings = values.findings.trim()
  const workPerformed = values.workPerformed.trim()
  const partsUsed = parsePartsUsed(values.partsUsed)

  if (findings.length > TEXT_MAX_LENGTH) {
    errors.findings = `Findings must be ${TEXT_MAX_LENGTH} characters or fewer.`
  }

  if (workPerformed.length > TEXT_MAX_LENGTH) {
    errors.workPerformed = `Work performed must be ${TEXT_MAX_LENGTH} characters or fewer.`
  }

  if (!findings && !workPerformed) {
    errors.workPerformed =
      'Enter findings or a description of the work performed.'
  }

  if (Object.keys(errors).length > 0) {
    return { isValid: false, errors, payload: null }
  }

  return {
    isValid: true,
    errors,
    payload: {
      findings: findings || null,
      work_performed: workPerformed || null,
      parts_used: partsUsed,
    },
  }
}

export interface CompletionReportFormValues {
  serviceRecordId: string
  summary: string
}

export function validateCompletionReportCreate(
  values: CompletionReportFormValues,
): ValidationResult<CompletionReportCreateRequest> {
  const errors: FieldErrors = {}
  const summary = values.summary.trim()

  if (!values.serviceRecordId) {
    errors.serviceRecordId = 'Choose the service record this report completes.'
  }

  if (!summary) {
    errors.summary = 'Summarize the completed work before submitting.'
  } else if (summary.length > TEXT_MAX_LENGTH) {
    errors.summary = `Summary must be ${TEXT_MAX_LENGTH} characters or fewer.`
  }

  if (Object.keys(errors).length > 0) {
    return { isValid: false, errors, payload: null }
  }

  return {
    isValid: true,
    errors,
    payload: {
      service_record_id: values.serviceRecordId,
      summary,
    },
  }
}

export function validateCompletionReportUpdate(
  summary: string,
): ValidationResult<CompletionReportUpdateRequest> {
  const errors: FieldErrors = {}
  const trimmed = summary.trim()

  if (!trimmed) {
    errors.summary = 'Summary cannot be blank.'
  } else if (trimmed.length > TEXT_MAX_LENGTH) {
    errors.summary = `Summary must be ${TEXT_MAX_LENGTH} characters or fewer.`
  }

  if (Object.keys(errors).length > 0) {
    return { isValid: false, errors, payload: null }
  }

  return {
    isValid: true,
    errors,
    payload: { summary: trimmed },
  }
}
