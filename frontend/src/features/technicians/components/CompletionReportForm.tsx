import { useRef, useState, type FormEvent } from 'react'
import { FormError } from '../../../components/Feedback'
import {
  FormField,
  inputClassName,
} from '../../../components/FormField'
import { apiErrorMessage, fieldErrorsFromApiError } from '../../../lib/api/errors'
import { createSubmissionGuard } from '../../../lib/forms/submission-guard'
import type { FieldErrors } from '../../../lib/forms/validation'
import type {
  CompletionReportCreateRequest,
  CompletionReportUpdateRequest,
  ServiceRecord,
} from '../../work-orders/types'
import {
  validateCompletionReportCreate,
  validateCompletionReportUpdate,
  type CompletionReportFormValues,
} from '../validation'

export function CompletionReportCreateForm({
  serviceRecords,
  isSubmitting,
  onSubmit,
  errorMessage,
}: {
  serviceRecords: readonly ServiceRecord[]
  isSubmitting: boolean
  onSubmit: (payload: CompletionReportCreateRequest) => Promise<void>
  errorMessage?: (error: unknown) => string
}) {
  const [values, setValues] = useState<CompletionReportFormValues>({
    serviceRecordId: serviceRecords[0]?.id ?? '',
    summary: '',
  })
  const [errors, setErrors] = useState<FieldErrors>({})
  const [apiError, setApiError] = useState<string | null>(null)
  const guardRef = useRef(createSubmissionGuard())

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (!guardRef.current.begin()) {
      return
    }

    const result = validateCompletionReportCreate(values)
    setErrors(result.errors)
    setApiError(null)

    if (!result.isValid || result.payload === null) {
      guardRef.current.end()
      return
    }

    try {
      await onSubmit(result.payload)
    } catch (caught) {
      const fieldErrors = fieldErrorsFromApiError(caught)
      const mapped: FieldErrors = {}
      if (fieldErrors.service_record_id) {
        mapped.serviceRecordId = fieldErrors.service_record_id
      }
      if (fieldErrors.summary) {
        mapped.summary = fieldErrors.summary
      }
      setErrors(mapped)
      setApiError(
        Object.keys(fieldErrors).length > 0
          ? 'Please correct the highlighted fields.'
          : errorMessage
            ? errorMessage(caught)
            : apiErrorMessage(caught, 'Unable to submit this completion report.'),
      )
    } finally {
      guardRef.current.end()
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="grid gap-4">
      <FormError message={apiError} />

      <FormField
        id="completion-report-service-record"
        label="Service record"
        hint="Choose the service record that documents the work performed."
        error={errors.serviceRecordId}
      >
        <select
          id="completion-report-service-record"
          className={inputClassName}
          value={values.serviceRecordId}
          aria-invalid={errors.serviceRecordId ? true : undefined}
          onChange={(event) =>
            setValues((current) => ({
              ...current,
              serviceRecordId: event.target.value,
            }))
          }
        >
          {serviceRecords.map((record) => (
            <option key={record.id} value={record.id}>
              {record.recorded_at} - {record.work_performed ?? record.findings ?? 'Service record'}
            </option>
          ))}
        </select>
      </FormField>

      <FormField
        id="completion-report-summary"
        label="Completion summary"
        required
        hint="Describe the completed repair and the final state of the equipment."
        error={errors.summary}
      >
        <textarea
          id="completion-report-summary"
          className={`${inputClassName} min-h-32 resize-y`}
          value={values.summary}
          maxLength={10000}
          required
          aria-invalid={errors.summary ? true : undefined}
          onChange={(event) =>
            setValues((current) => ({
              ...current,
              summary: event.target.value,
            }))
          }
        />
      </FormField>

      <div className="flex justify-end">
        <button
          type="submit"
          disabled={isSubmitting || serviceRecords.length === 0}
          className="rounded-xl bg-sky-500 px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-sky-400 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isSubmitting ? 'Submitting...' : 'Submit completion report'}
        </button>
      </div>
    </form>
  )
}

export function CompletionReportEditForm({
  initialSummary,
  isSubmitting,
  onSubmit,
  onCancel,
  errorMessage,
}: {
  initialSummary: string
  isSubmitting: boolean
  onSubmit: (payload: CompletionReportUpdateRequest) => Promise<void>
  onCancel: () => void
  errorMessage?: (error: unknown) => string
}) {
  const [summary, setSummary] = useState(initialSummary)
  const [errors, setErrors] = useState<FieldErrors>({})
  const [apiError, setApiError] = useState<string | null>(null)
  const guardRef = useRef(createSubmissionGuard())

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (!guardRef.current.begin()) {
      return
    }

    const result = validateCompletionReportUpdate(summary)
    setErrors(result.errors)
    setApiError(null)

    if (!result.isValid || result.payload === null) {
      guardRef.current.end()
      return
    }

    try {
      await onSubmit(result.payload)
    } catch (caught) {
      const fieldErrors = fieldErrorsFromApiError(caught)
      const mapped: FieldErrors = {}
      if (fieldErrors.summary) {
        mapped.summary = fieldErrors.summary
      }
      setErrors(mapped)
      setApiError(
        Object.keys(fieldErrors).length > 0
          ? 'Please correct the highlighted fields.'
          : errorMessage
            ? errorMessage(caught)
            : apiErrorMessage(caught, 'Unable to update this completion report.'),
      )
    } finally {
      guardRef.current.end()
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="grid gap-4">
      <FormError message={apiError} />

      <FormField
        id="completion-report-edit-summary"
        label="Completion summary"
        required
        error={errors.summary}
      >
        <textarea
          id="completion-report-edit-summary"
          className={`${inputClassName} min-h-28 resize-y`}
          value={summary}
          maxLength={10000}
          required
          aria-invalid={errors.summary ? true : undefined}
          onChange={(event) => setSummary(event.target.value)}
        />
      </FormField>

      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          disabled={isSubmitting}
          className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-medium text-slate-200 transition hover:border-slate-500 disabled:cursor-not-allowed disabled:opacity-60"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={isSubmitting}
          className="rounded-xl bg-sky-500 px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-sky-400 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isSubmitting ? 'Saving...' : 'Save summary'}
        </button>
      </div>
    </form>
  )
}
