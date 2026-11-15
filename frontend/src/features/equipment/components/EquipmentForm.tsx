import {
  useRef,
  useState,
  type FormEvent,
} from 'react'
import { FormError } from '../../../components/Feedback'
import {
  FormField,
  inputClassName,
} from '../../../components/FormField'
import { apiErrorMessage, fieldErrorsFromApiError } from '../../../lib/api/errors'
import { createSubmissionGuard } from '../../../lib/forms/submission-guard'
import type { FieldErrors } from '../../../lib/forms/validation'
import type {
  Equipment,
  EquipmentCreateRequest,
} from '../types'
import {
  validateEquipmentForm,
  type EquipmentFormValues,
} from '../validation'

function initialValues(equipment?: Equipment): EquipmentFormValues {
  return {
    manufacturer: equipment?.manufacturer ?? '',
    model: equipment?.model ?? '',
    serialNumber: equipment?.serial_number ?? '',
    equipmentType: equipment?.equipment_type ?? '',
    installationDate: equipment?.installation_date ?? '',
  }
}

function localToday(): string {
  const today = new Date()
  const year = today.getFullYear()
  const month = String(today.getMonth() + 1).padStart(2, '0')
  const day = String(today.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function EquipmentForm({
  equipment,
  submitLabel,
  onSubmit,
}: {
  equipment?: Equipment
  submitLabel: string
  onSubmit: (payload: EquipmentCreateRequest) => Promise<void>
}) {
  const [values, setValues] = useState<EquipmentFormValues>(() =>
    initialValues(equipment),
  )
  const [errors, setErrors] = useState<FieldErrors>({})
  const [apiError, setApiError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const guardRef = useRef(createSubmissionGuard())

  function update(field: keyof EquipmentFormValues, value: string) {
    setValues((current) => ({ ...current, [field]: value }))
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (!guardRef.current.begin()) {
      return
    }

    const result = validateEquipmentForm(values)
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
      if (fieldErrors.manufacturer) {
        mapped.manufacturer = fieldErrors.manufacturer
      }
      if (fieldErrors.model) {
        mapped.model = fieldErrors.model
      }
      if (fieldErrors.serial_number) {
        mapped.serialNumber = fieldErrors.serial_number
      }
      if (fieldErrors.equipment_type) {
        mapped.equipmentType = fieldErrors.equipment_type
      }
      if (fieldErrors.installation_date) {
        mapped.installationDate = fieldErrors.installation_date
      }
      setErrors(mapped)
      setApiError(
        Object.keys(fieldErrors).length > 0
          ? 'Please correct the highlighted fields.'
          : apiErrorMessage(caught, 'Unable to save this equipment.'),
      )
    } finally {
      setIsSubmitting(false)
      guardRef.current.end()
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="grid gap-5">
      <FormError message={apiError} />

      <div className="grid gap-4 sm:grid-cols-2">
        <FormField
          id="equipment-manufacturer"
          label="Manufacturer"
          required
          error={errors.manufacturer}
        >
          <input
            id="equipment-manufacturer"
            className={inputClassName}
            value={values.manufacturer}
            maxLength={150}
            required
            aria-invalid={errors.manufacturer ? true : undefined}
            aria-describedby={
              errors.manufacturer
                ? 'equipment-manufacturer-error'
                : undefined
            }
            onChange={(event) => update('manufacturer', event.target.value)}
          />
        </FormField>

        <FormField
          id="equipment-model"
          label="Model"
          required
          error={errors.model}
        >
          <input
            id="equipment-model"
            className={inputClassName}
            value={values.model}
            maxLength={150}
            required
            aria-invalid={errors.model ? true : undefined}
            aria-describedby={
              errors.model ? 'equipment-model-error' : undefined
            }
            onChange={(event) => update('model', event.target.value)}
          />
        </FormField>

        <FormField
          id="equipment-type"
          label="Equipment type"
          required
          hint="For example solar inverter, battery, or meter."
          error={errors.equipmentType}
        >
          <input
            id="equipment-type"
            className={inputClassName}
            value={values.equipmentType}
            maxLength={80}
            required
            aria-invalid={errors.equipmentType ? true : undefined}
            aria-describedby={
              errors.equipmentType
                ? 'equipment-type-error'
                : 'equipment-type-hint'
            }
            onChange={(event) => update('equipmentType', event.target.value)}
          />
        </FormField>

        <FormField
          id="equipment-serial"
          label="Serial number"
          hint="Optional. Manufacturer and serial number must be unique."
          error={errors.serialNumber}
        >
          <input
            id="equipment-serial"
            className={inputClassName}
            value={values.serialNumber}
            maxLength={150}
            aria-invalid={errors.serialNumber ? true : undefined}
            aria-describedby={
              errors.serialNumber
                ? 'equipment-serial-error'
                : 'equipment-serial-hint'
            }
            onChange={(event) => update('serialNumber', event.target.value)}
          />
        </FormField>

        <FormField
          id="equipment-installation-date"
          label="Installation date"
          hint="Optional. Future dates are not accepted."
          error={errors.installationDate}
        >
          <input
            id="equipment-installation-date"
            type="date"
            max={localToday()}
            className={inputClassName}
            value={values.installationDate}
            aria-invalid={errors.installationDate ? true : undefined}
            aria-describedby={
              errors.installationDate
                ? 'equipment-installation-date-error'
                : 'equipment-installation-date-hint'
            }
            onChange={(event) => update('installationDate', event.target.value)}
          />
        </FormField>
      </div>

      <div className="flex justify-end">
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
