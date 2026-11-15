import type { FieldErrors, ValidationResult } from '../../lib/forms/validation.ts'
import type { EquipmentCreateRequest } from './types'

export interface EquipmentFormValues {
  manufacturer: string
  model: string
  serialNumber: string
  equipmentType: string
  installationDate: string
}

const MANUFACTURER_MAX_LENGTH = 150
const MODEL_MAX_LENGTH = 150
const TYPE_MAX_LENGTH = 80
const SERIAL_MAX_LENGTH = 150

function formatLocalDate(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function isValidDateString(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return false
  }

  const [year, month, day] = value.split('-').map(Number)
  const parsed = new Date(Date.UTC(year, month - 1, day))

  return (
    parsed.getUTCFullYear() === year &&
    parsed.getUTCMonth() === month - 1 &&
    parsed.getUTCDate() === day
  )
}

export function validateEquipmentForm(
  values: EquipmentFormValues,
  today: Date = new Date(),
): ValidationResult<EquipmentCreateRequest> {
  const errors: FieldErrors = {}
  const manufacturer = values.manufacturer.trim()
  const model = values.model.trim()
  const serialNumber = values.serialNumber.trim()
  const equipmentType = values.equipmentType.trim()
  const installationDate = values.installationDate.trim()

  if (!manufacturer) {
    errors.manufacturer = 'Manufacturer is required.'
  } else if (manufacturer.length > MANUFACTURER_MAX_LENGTH) {
    errors.manufacturer = `Manufacturer must be ${MANUFACTURER_MAX_LENGTH} characters or fewer.`
  }

  if (!model) {
    errors.model = 'Model is required.'
  } else if (model.length > MODEL_MAX_LENGTH) {
    errors.model = `Model must be ${MODEL_MAX_LENGTH} characters or fewer.`
  }

  if (!equipmentType) {
    errors.equipmentType = 'Equipment type is required.'
  } else if (equipmentType.length > TYPE_MAX_LENGTH) {
    errors.equipmentType = `Equipment type must be ${TYPE_MAX_LENGTH} characters or fewer.`
  }

  if (serialNumber.length > SERIAL_MAX_LENGTH) {
    errors.serialNumber = `Serial number must be ${SERIAL_MAX_LENGTH} characters or fewer.`
  }

  if (installationDate) {
    if (!isValidDateString(installationDate)) {
      errors.installationDate = 'Enter a valid installation date.'
    } else if (installationDate > formatLocalDate(today)) {
      errors.installationDate = 'Installation date cannot be in the future.'
    }
  }

  if (Object.keys(errors).length > 0) {
    return { isValid: false, errors, payload: null }
  }

  const payload = {
    manufacturer,
    model,
    serial_number: serialNumber || null,
    equipment_type: equipmentType,
    installation_date: installationDate || null,
  }

  return { isValid: true, errors, payload }
}
