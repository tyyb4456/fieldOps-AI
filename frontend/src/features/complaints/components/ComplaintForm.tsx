import {
  useRef,
  useState,
  type FormEvent,
} from 'react'
import { FormError, InlineWarning } from '../../../components/Feedback'
import {
  FormField,
  inputClassName,
} from '../../../components/FormField'
import { apiErrorMessage, fieldErrorsFromApiError } from '../../../lib/api/errors'
import { createSubmissionGuard } from '../../../lib/forms/submission-guard'
import type { FieldErrors } from '../../../lib/forms/validation'
import type { Equipment } from '../../equipment/types'
import type { ComplaintCreateRequest } from '../types'
import {
  validateComplaintForm,
  type ComplaintFormValues,
} from '../validation'

export function ComplaintForm({
  equipment,
  isEquipmentLoading,
  equipmentLoadError,
  onRetryEquipment,
  onSubmit,
}: {
  equipment: readonly Equipment[]
  isEquipmentLoading: boolean
  equipmentLoadError: boolean
  onRetryEquipment: () => void
  onSubmit: (payload: ComplaintCreateRequest) => Promise<void>
}) {
  const [values, setValues] = useState<ComplaintFormValues>({
    description: '',
    equipmentId: '',
    errorCode: '',
  })
  const [errors, setErrors] = useState<FieldErrors>({})
  const [apiError, setApiError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const guardRef = useRef(createSubmissionGuard())

  function update(field: keyof ComplaintFormValues, value: string) {
    setValues((current) => ({ ...current, [field]: value }))
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (!guardRef.current.begin()) {
      return
    }

    const result = validateComplaintForm(
      values,
      equipment.map((item) => item.id),
    )
    setErrors(result.errors)
    setApiError(null)

    if (!result.isValid || result.payload === null) {
      guardRef.current.end()
      return
    }

    setIsSubmitting(true)
    try {
      await onSubmit(result.payload)
    } catch (caught) {
      const fieldErrors = fieldErrorsFromApiError(caught)
      const mapped: FieldErrors = {}
      if (fieldErrors.description) {
        mapped.description = fieldErrors.description
      }
      if (fieldErrors.equipment_id) {
        mapped.equipmentId = fieldErrors.equipment_id
      }
      if (fieldErrors.reported_error_code) {
        mapped.errorCode = fieldErrors.reported_error_code
      }
      setErrors(mapped)
      setApiError(
        Object.keys(fieldErrors).length > 0
          ? 'Please correct the highlighted fields.'
          : apiErrorMessage(
              caught,
              'Unable to submit your complaint. Please try again.',
            ),
      )
    } finally {
      setIsSubmitting(false)
      guardRef.current.end()
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="grid gap-5">
      <FormError message={apiError} />

      {equipmentLoadError ? (
        <InlineWarning>
          We could not load your equipment list. You can still submit a
          description without equipment.{' '}
          <button
            type="button"
            onClick={onRetryEquipment}
            className="font-semibold underline underline-offset-2"
          >
            Retry equipment list
          </button>
        </InlineWarning>
      ) : null}

      {!isEquipmentLoading &&
      !equipmentLoadError &&
      equipment.length === 0 ? (
        <InlineWarning>
          You have no registered equipment yet. You can submit this complaint
          without selecting equipment.
        </InlineWarning>
      ) : null}

      <FormField
        id="complaint-equipment"
        label="Equipment"
        hint="Choose one of your registered equipment records, or leave this blank."
        error={errors.equipmentId}
      >
        <select
          id="complaint-equipment"
          className={inputClassName}
          value={values.equipmentId}
          disabled={isEquipmentLoading || equipmentLoadError}
          aria-invalid={errors.equipmentId ? true : undefined}
          aria-describedby={
            errors.equipmentId
              ? 'complaint-equipment-error'
              : 'complaint-equipment-hint'
          }
          onChange={(event) => update('equipmentId', event.target.value)}
        >
          <option value="">
            {isEquipmentLoading ? 'Loading equipment...' : 'No specific equipment'}
          </option>
          {equipment.map((item) => (
            <option key={item.id} value={item.id}>
              {item.manufacturer} {item.model} ({item.equipment_type})
            </option>
          ))}
        </select>
      </FormField>

      <FormField
        id="complaint-description"
        label="Describe the problem"
        required
        hint="At least 5 characters. Include what happened and when it started."
        error={errors.description}
      >
        <textarea
          id="complaint-description"
          className={`${inputClassName} min-h-40 resize-y`}
          value={values.description}
          maxLength={10000}
          required
          aria-invalid={errors.description ? true : undefined}
          aria-describedby={
            errors.description
              ? 'complaint-description-error'
              : 'complaint-description-hint'
          }
          onChange={(event) => update('description', event.target.value)}
        />
      </FormField>

      <FormField
        id="complaint-error-code"
        label="Error code"
        hint="Optional. Enter the code shown on the equipment display."
        error={errors.errorCode}
      >
        <input
          id="complaint-error-code"
          className={inputClassName}
          value={values.errorCode}
          maxLength={100}
          aria-invalid={errors.errorCode ? true : undefined}
          aria-describedby={
            errors.errorCode
              ? 'complaint-error-code-error'
              : 'complaint-error-code-hint'
          }
          onChange={(event) => update('errorCode', event.target.value)}
        />
      </FormField>

      <p className="text-xs leading-5 text-slate-500">
        Submitting a complaint records it for review. It does not start a
        diagnostic investigation automatically.
      </p>

      <div className="flex justify-end">
        <button
          type="submit"
          disabled={isSubmitting}
          className="rounded-xl bg-sky-500 px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-sky-400 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isSubmitting ? 'Submitting...' : 'Submit complaint'}
        </button>
      </div>
    </form>
  )
}
