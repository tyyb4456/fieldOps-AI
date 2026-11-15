import { useRef, useState, type FormEvent } from 'react'
import { FormError } from '../../../components/Feedback'
import {
  FormField,
  inputClassName,
} from '../../../components/FormField'
import { fieldErrorsFromApiError } from '../../../lib/api/errors'
import { createSubmissionGuard } from '../../../lib/forms/submission-guard'
import type { FieldErrors } from '../../../lib/forms/validation'
import type {
  EquipmentCreateRequest,
  EquipmentUpdateRequest,
} from '../../equipment/types'
import {
  validateEquipmentCreate,
  validateEquipmentUpdate,
  type EquipmentFormValues,
} from '../validation'

export type EquipmentFormMode = 'create' | 'edit'

export function EquipmentForm({
  mode,
  initial,
  submitLabel,
  isSubmitting,
  onSubmit,
  onCancel,
  errorMessage,
}: {
  mode: EquipmentFormMode
  initial: EquipmentFormValues
  submitLabel: string
  isSubmitting: boolean
  onSubmit: (
    payload: EquipmentCreateRequest | EquipmentUpdateRequest,
  ) => Promise<void>
  onCancel?: () => void
  errorMessage: (error: unknown) => string
}) {
  const [values, setValues] = useState<EquipmentFormValues>(initial)
  const [errors, setErrors] = useState<FieldErrors>({})
  const [apiError, setApiError] = useState<string | null>(null)
  const guardRef = useRef(createSubmissionGuard())

  function update<K extends keyof EquipmentFormValues>(
    field: K,
    value: EquipmentFormValues[K],
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
        ? validateEquipmentCreate(values)
        : validateEquipmentUpdate(values)
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
      if (fieldErrors.manufacturer) {
        mapped.manufacturer = fieldErrors.manufacturer
      }
      if (fieldErrors.model) {
        mapped.model = fieldErrors.model
      }
      if (fieldErrors.equipment_type) {
        mapped.equipmentType = fieldErrors.equipment_type
      }
      if (fieldErrors.serial_number) {
        mapped.serialNumber = fieldErrors.serial_number
      }
      if (fieldErrors.installation_date) {
        mapped.installationDate = fieldErrors.installation_date
      }
      setErrors(mapped)
      setApiError(
        Object.keys(fieldErrors).length > 0
          ? 'Please correct the highlighted fields.'
          : errorMessage(caught),
      )
    } finally {
      guardRef.current.end()
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="grid gap-4">
      <FormError message={apiError} />
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField
          id="admin-equipment-manufacturer"
          label="Manufacturer"
          required
          error={errors.manufacturer}
        >
          <input
            id="admin-equipment-manufacturer"
            className={inputClassName}
            value={values.manufacturer}
            maxLength={150}
            onChange={(event) => update('manufacturer', event.target.value)}
          />
        </FormField>
        <FormField
          id="admin-equipment-model"
          label="Model"
          required
          error={errors.model}
        >
          <input
            id="admin-equipment-model"
            className={inputClassName}
            value={values.model}
            maxLength={150}
            onChange={(event) => update('model', event.target.value)}
          />
        </FormField>
        <FormField
          id="admin-equipment-type"
          label="Equipment type"
          required
          error={errors.equipmentType}
        >
          <input
            id="admin-equipment-type"
            className={inputClassName}
            value={values.equipmentType}
            maxLength={80}
            onChange={(event) => update('equipmentType', event.target.value)}
          />
        </FormField>
        <FormField
          id="admin-equipment-serial"
          label="Serial number"
          error={errors.serialNumber}
        >
          <input
            id="admin-equipment-serial"
            className={inputClassName}
            value={values.serialNumber}
            maxLength={120}
            onChange={(event) => update('serialNumber', event.target.value)}
          />
        </FormField>
        <FormField
          id="admin-equipment-installation"
          label="Installation date"
          error={errors.installationDate}
        >
          <input
            id="admin-equipment-installation"
            type="date"
            className={inputClassName}
            value={values.installationDate}
            onChange={(event) => update('installationDate', event.target.value)}
          />
        </FormField>
      </div>
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
