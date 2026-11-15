import { useRef, useState, type FormEvent } from 'react'
import { FormError } from '../../../components/Feedback'
import {
  FormField,
  inputClassName,
} from '../../../components/FormField'
import { apiErrorMessage, fieldErrorsFromApiError } from '../../../lib/api/errors'
import type { Priority } from '../../../lib/api/types'
import { PRIORITIES } from '../../../lib/api/types'
import { createSubmissionGuard } from '../../../lib/forms/submission-guard'
import type { FieldErrors } from '../../../lib/forms/validation'
import { priorityLabel } from '../../complaints/labels'
import type {
  WorkOrderCreateRequest,
  WorkOrderUpdateRequest,
} from '../../work-orders/types'
import {
  validateWorkOrderCreate,
  validateWorkOrderUpdate,
  type WorkOrderCreateFormValues,
} from '../validation'

export type WorkOrderFormMode = 'create' | 'edit'

export function WorkOrderForm({
  mode,
  initial,
  submitLabel,
  isSubmitting,
  onSubmit,
  onCancel,
  errorMessage,
}: {
  mode: WorkOrderFormMode
  initial: WorkOrderCreateFormValues
  submitLabel: string
  isSubmitting: boolean
  onSubmit: (
    payload: WorkOrderCreateRequest | WorkOrderUpdateRequest,
  ) => Promise<void>
  onCancel?: () => void
  errorMessage?: (error: unknown) => string
}) {
  const [values, setValues] = useState<WorkOrderCreateFormValues>(initial)
  const [errors, setErrors] = useState<FieldErrors>({})
  const [apiError, setApiError] = useState<string | null>(null)
  const guardRef = useRef(createSubmissionGuard())

  function update<K extends keyof WorkOrderCreateFormValues>(
    field: K,
    value: WorkOrderCreateFormValues[K],
  ) {
    setValues((current) => ({ ...current, [field]: value }))
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (!guardRef.current.begin()) {
      return
    }

    const result =
      mode === 'create'
        ? validateWorkOrderCreate(values)
        : validateWorkOrderUpdate(values)
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
      if (fieldErrors.title) {
        mapped.title = fieldErrors.title
      }
      if (fieldErrors.description) {
        mapped.description = fieldErrors.description
      }
      if (fieldErrors.priority) {
        mapped.priority = fieldErrors.priority
      }
      setErrors(mapped)
      setApiError(
        Object.keys(fieldErrors).length > 0
          ? 'Please correct the highlighted fields.'
          : errorMessage
            ? errorMessage(caught)
            : apiErrorMessage(caught, 'Unable to save this work order.'),
      )
    } finally {
      guardRef.current.end()
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="grid gap-4">
      <FormError message={apiError} />

      <FormField
        id="admin-work-order-title"
        label="Title"
        required
        error={errors.title}
      >
        <input
          id="admin-work-order-title"
          className={inputClassName}
          value={values.title}
          maxLength={255}
          required
          aria-invalid={errors.title ? true : undefined}
          onChange={(event) => update('title', event.target.value)}
        />
      </FormField>

      <FormField
        id="admin-work-order-description"
        label="Description"
        required
        error={errors.description}
      >
        <textarea
          id="admin-work-order-description"
          className={`${inputClassName} min-h-32 resize-y`}
          value={values.description}
          maxLength={10000}
          required
          aria-invalid={errors.description ? true : undefined}
          onChange={(event) => update('description', event.target.value)}
        />
      </FormField>

      <FormField
        id="admin-work-order-priority"
        label="Priority"
        error={errors.priority}
      >
        <select
          id="admin-work-order-priority"
          className={inputClassName}
          value={values.priority}
          onChange={(event) =>
            update('priority', event.target.value as Priority)
          }
        >
          {PRIORITIES.map((priority) => (
            <option key={priority} value={priority}>
              {priorityLabel(priority)}
            </option>
          ))}
        </select>
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
