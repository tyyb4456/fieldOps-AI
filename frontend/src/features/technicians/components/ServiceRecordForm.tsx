import { useRef, useState, type FormEvent } from 'react'
import { FormError } from '../../../components/Feedback'
import {
  FormField,
  inputClassName,
} from '../../../components/FormField'
import { apiErrorMessage, fieldErrorsFromApiError } from '../../../lib/api/errors'
import { createSubmissionGuard } from '../../../lib/forms/submission-guard'
import type { FieldErrors } from '../../../lib/forms/validation'
import type { ServiceRecordCreateRequest } from '../../work-orders/types'
import {
  validateServiceRecordForm,
  type ServiceRecordFormValues,
} from '../validation'

export function ServiceRecordForm({
  initial,
  submitLabel,
  isSubmitting,
  onSubmit,
  onCancel,
  errorMessage,
}: {
  initial: ServiceRecordFormValues
  submitLabel: string
  isSubmitting: boolean
  onSubmit: (payload: ServiceRecordCreateRequest) => Promise<void>
  onCancel?: () => void
  errorMessage?: (error: unknown) => string
}) {
  const [values, setValues] = useState<ServiceRecordFormValues>(initial)
  const [errors, setErrors] = useState<FieldErrors>({})
  const [apiError, setApiError] = useState<string | null>(null)
  const guardRef = useRef(createSubmissionGuard())

  function update(field: keyof ServiceRecordFormValues, value: string) {
    setValues((current) => ({ ...current, [field]: value }))
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (!guardRef.current.begin()) {
      return
    }

    const result = validateServiceRecordForm(values)
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
      if (fieldErrors.findings) {
        mapped.findings = fieldErrors.findings
      }
      if (fieldErrors.work_performed) {
        mapped.workPerformed = fieldErrors.work_performed
      }
      if (fieldErrors.parts_used) {
        mapped.partsUsed = fieldErrors.parts_used
      }
      setErrors(mapped)
      setApiError(
        Object.keys(fieldErrors).length > 0
          ? 'Please correct the highlighted fields.'
          : errorMessage
            ? errorMessage(caught)
            : apiErrorMessage(caught, 'Unable to save this service record.'),
      )
    } finally {
      guardRef.current.end()
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="grid gap-4">
      <FormError message={apiError} />

      <FormField
        id="service-record-findings"
        label="Findings"
        hint="Optional. What you observed during the visit."
        error={errors.findings}
      >
        <textarea
          id="service-record-findings"
          className={`${inputClassName} min-h-28 resize-y`}
          value={values.findings}
          maxLength={10000}
          aria-invalid={errors.findings ? true : undefined}
          onChange={(event) => update('findings', event.target.value)}
        />
      </FormField>

      <FormField
        id="service-record-work-performed"
        label="Work performed"
        hint="Required if findings are empty. Describe the work you completed."
        error={errors.workPerformed}
      >
        <textarea
          id="service-record-work-performed"
          className={`${inputClassName} min-h-28 resize-y`}
          value={values.workPerformed}
          maxLength={10000}
          aria-invalid={errors.workPerformed ? true : undefined}
          onChange={(event) => update('workPerformed', event.target.value)}
        />
      </FormField>

      <FormField
        id="service-record-parts-used"
        label="Parts used"
        hint="Optional. Enter one part per line."
        error={errors.partsUsed}
      >
        <textarea
          id="service-record-parts-used"
          className={`${inputClassName} min-h-20 resize-y`}
          value={values.partsUsed}
          aria-invalid={errors.partsUsed ? true : undefined}
          onChange={(event) => update('partsUsed', event.target.value)}
        />
      </FormField>

      <div className="flex flex-wrap justify-end gap-2">
        {onCancel ? (
          <button
            type="button"
            onClick={onCancel}
            disabled={isSubmitting}
            className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-medium text-slate-200 transition hover:border-slate-500 disabled:cursor-not-allowed disabled:opacity-60"
          >
            Cancel
          </button>
        ) : null}
        <button
          type="submit"
          disabled={isSubmitting}
          className="rounded-xl bg-sky-500 px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-sky-400 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isSubmitting ? 'Saving...' : submitLabel}
        </button>
      </div>
    </form>
  )
}
