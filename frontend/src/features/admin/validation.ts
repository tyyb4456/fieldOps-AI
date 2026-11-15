import type {
  FieldErrors,
  ValidationResult,
} from '../../lib/forms/validation.ts'
import type { Priority } from '../../lib/api/types'
import type {
  DocumentUpdateRequest,
  DocumentUploadFields,
} from '../documents/types'
import type {
  EquipmentCreateRequest,
  EquipmentUpdateRequest,
} from '../equipment/types'
import type {
  CompletionReportUpdateRequest,
  WorkOrderCreateRequest,
  WorkOrderUpdateRequest,
} from '../work-orders/types'

export interface WorkOrderCreateFormValues {
  title: string
  description: string
  priority: Priority
}

export const EMPTY_WORK_ORDER_CREATE_FORM: WorkOrderCreateFormValues = {
  title: '',
  description: '',
  priority: 'normal',
}

export function validateWorkOrderCreate(
  values: WorkOrderCreateFormValues,
): ValidationResult<WorkOrderCreateRequest> {
  const errors: FieldErrors = {}
  const title = values.title.trim()
  const description = values.description.trim()

  if (!title) {
    errors.title = 'Enter a title for the work order.'
  } else if (title.length > 255) {
    errors.title = 'Title must be 255 characters or fewer.'
  }

  if (!description) {
    errors.description = 'Describe the work to be performed.'
  } else if (description.length > 10000) {
    errors.description = 'Description must be 10000 characters or fewer.'
  }

  if (Object.keys(errors).length > 0) {
    return { isValid: false, errors, payload: null }
  }

  return {
    isValid: true,
    errors,
    payload: { title, description, priority: values.priority },
  }
}

export interface WorkOrderEditFormValues {
  title: string
  description: string
  priority: Priority
}

export function validateWorkOrderUpdate(
  values: WorkOrderEditFormValues,
): ValidationResult<WorkOrderUpdateRequest> {
  const errors: FieldErrors = {}
  const title = values.title.trim()
  const description = values.description.trim()

  if (!title) {
    errors.title = 'Enter a title for the work order.'
  } else if (title.length > 255) {
    errors.title = 'Title must be 255 characters or fewer.'
  }

  if (!description) {
    errors.description = 'Describe the work to be performed.'
  } else if (description.length > 10000) {
    errors.description = 'Description must be 10000 characters or fewer.'
  }

  if (Object.keys(errors).length > 0) {
    return { isValid: false, errors, payload: null }
  }

  return {
    isValid: true,
    errors,
    payload: { title, description, priority: values.priority },
  }
}

export function validateAssignmentTechnician(
  technicianId: string,
): ValidationResult<string> {
  if (!technicianId) {
    return {
      isValid: false,
      errors: { technicianId: 'Choose an eligible technician.' },
      payload: null,
    }
  }
  return { isValid: true, errors: {}, payload: technicianId }
}

export function validateProposalReject(
  reason: string,
): ValidationResult<string> {
  const trimmed = reason.trim()
  if (trimmed.length < 3) {
    return {
      isValid: false,
      errors: {
        reason: 'Enter a rejection reason of at least 3 characters.',
      },
      payload: null,
    }
  }
  if (trimmed.length > 2000) {
    return {
      isValid: false,
      errors: { reason: 'Reason must be 2000 characters or fewer.' },
      payload: null,
    }
  }
  return { isValid: true, errors: {}, payload: trimmed }
}

export type VerificationAction = 'verified' | 'rejected'

export function validateCompletionVerification(
  action: VerificationAction,
  notes: string,
): ValidationResult<CompletionReportUpdateRequest> {
  const trimmed = notes.trim()
  const errors: FieldErrors = {}

  if (action === 'rejected' && !trimmed) {
    errors.verificationNotes =
      'Add notes explaining why this evidence is rejected.'
  }
  if (trimmed.length > 10000) {
    errors.verificationNotes =
      'Verification notes must be 10000 characters or fewer.'
  }

  if (Object.keys(errors).length > 0) {
    return { isValid: false, errors, payload: null }
  }

  return {
    isValid: true,
    errors,
    payload: {
      evidence_status: action,
      verification_notes: trimmed || null,
    },
  }
}

export interface DocumentUploadFormValues {
  file: File | null
  manufacturer: string
  model: string
  documentName: string
  version: string
}

export const EMPTY_DOCUMENT_UPLOAD_FORM: DocumentUploadFormValues = {
  file: null,
  manufacturer: '',
  model: '',
  documentName: '',
  version: '',
}

export function validateDocumentUpload(
  values: DocumentUploadFormValues,
): ValidationResult<DocumentUploadFields> {
  const errors: FieldErrors = {}
  const manufacturer = values.manufacturer.trim()
  const model = values.model.trim()
  const documentName = values.documentName.trim()
  const version = values.version.trim()

  if (!values.file) {
    errors.file = 'Choose a PDF file to upload.'
  }
  if (!manufacturer) {
    errors.manufacturer = 'Enter the manufacturer.'
  } else if (manufacturer.length > 150) {
    errors.manufacturer = 'Manufacturer must be 150 characters or fewer.'
  }
  if (!model) {
    errors.model = 'Enter the equipment model.'
  } else if (model.length > 150) {
    errors.model = 'Model must be 150 characters or fewer.'
  }
  if (!documentName) {
    errors.documentName = 'Enter a document name.'
  } else if (documentName.length > 255) {
    errors.documentName = 'Document name must be 255 characters or fewer.'
  }
  if (version.length > 100) {
    errors.version = 'Version must be 100 characters or fewer.'
  }

  if (Object.keys(errors).length > 0 || !values.file) {
    return { isValid: false, errors, payload: null }
  }

  return {
    isValid: true,
    errors,
    payload: {
      file: values.file,
      manufacturer,
      model,
      document_name: documentName,
      version: version || null,
    },
  }
}

export interface DocumentMetadataFormValues {
  manufacturer: string
  model: string
  documentName: string
  version: string
}

export function validateDocumentMetadata(
  values: DocumentMetadataFormValues,
): ValidationResult<DocumentUpdateRequest> {
  const errors: FieldErrors = {}
  const manufacturer = values.manufacturer.trim()
  const model = values.model.trim()
  const documentName = values.documentName.trim()
  const version = values.version.trim()

  if (!manufacturer) {
    errors.manufacturer = 'Enter the manufacturer.'
  }
  if (!model) {
    errors.model = 'Enter the equipment model.'
  }
  if (!documentName) {
    errors.documentName = 'Enter a document name.'
  }

  if (Object.keys(errors).length > 0) {
    return { isValid: false, errors, payload: null }
  }

  return {
    isValid: true,
    errors,
    payload: {
      manufacturer,
      model,
      document_name: documentName,
      version: version || null,
    },
  }
}

export interface EquipmentFormValues {
  manufacturer: string
  model: string
  serialNumber: string
  equipmentType: string
  installationDate: string
}

export function validateEquipmentCreate(
  values: EquipmentFormValues,
): ValidationResult<EquipmentCreateRequest> {
  const errors: FieldErrors = {}
  const manufacturer = values.manufacturer.trim()
  const model = values.model.trim()
  const equipmentType = values.equipmentType.trim()

  if (!manufacturer) {
    errors.manufacturer = 'Enter the manufacturer.'
  }
  if (!model) {
    errors.model = 'Enter the equipment model.'
  }
  if (!equipmentType) {
    errors.equipmentType = 'Enter the equipment type.'
  }
  if (
    values.installationDate &&
    values.installationDate > new Date().toISOString().slice(0, 10)
  ) {
    errors.installationDate = 'Installation date cannot be in the future.'
  }

  if (Object.keys(errors).length > 0) {
    return { isValid: false, errors, payload: null }
  }

  return {
    isValid: true,
    errors,
    payload: {
      manufacturer,
      model,
      serial_number: values.serialNumber.trim() || null,
      equipment_type: equipmentType,
      installation_date: values.installationDate || null,
    },
  }
}

export function validateEquipmentUpdate(
  values: EquipmentFormValues,
): ValidationResult<EquipmentUpdateRequest> {
  const result = validateEquipmentCreate(values)
  if (!result.isValid || result.payload === null) {
    return { isValid: false, errors: result.errors, payload: null }
  }
  return { isValid: true, errors: result.errors, payload: result.payload }
}

export function validateCustomerId(
  customerId: string,
): ValidationResult<string> {
  const trimmed = customerId.trim()
  if (!trimmed) {
    return {
      isValid: false,
      errors: { customerId: 'Enter a customer identifier.' },
      payload: null,
    }
  }
  return { isValid: true, errors: {}, payload: trimmed }
}
