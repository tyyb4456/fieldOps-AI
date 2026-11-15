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
  DocumentUpdateRequest,
  DocumentUploadFields,
} from '../../documents/types'
import {
  EMPTY_DOCUMENT_UPLOAD_FORM,
  validateDocumentMetadata,
  validateDocumentUpload,
  type DocumentMetadataFormValues,
  type DocumentUploadFormValues,
} from '../validation'

export function DocumentUploadForm({
  isSubmitting,
  onSubmit,
  errorMessage,
}: {
  isSubmitting: boolean
  onSubmit: (fields: DocumentUploadFields) => Promise<void>
  errorMessage: (error: unknown) => string
}) {
  const [values, setValues] = useState<DocumentUploadFormValues>(
    EMPTY_DOCUMENT_UPLOAD_FORM,
  )
  const [errors, setErrors] = useState<FieldErrors>({})
  const [apiError, setApiError] = useState<string | null>(null)
  const guardRef = useRef(createSubmissionGuard())

  function update<K extends keyof DocumentUploadFormValues>(
    field: K,
    value: DocumentUploadFormValues[K],
  ) {
    setValues((current) => ({ ...current, [field]: value }))
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!guardRef.current.begin()) {
      return
    }
    const result = validateDocumentUpload(values)
    setErrors(result.errors)
    setApiError(null)
    if (!result.isValid || result.payload === null) {
      guardRef.current.end()
      return
    }
    try {
      await onSubmit(result.payload)
      setValues(EMPTY_DOCUMENT_UPLOAD_FORM)
    } catch (caught) {
      const fieldErrors = fieldErrorsFromApiError(caught)
      const mapped: FieldErrors = {}
      if (fieldErrors.file) {
        mapped.file = fieldErrors.file
      }
      if (fieldErrors.manufacturer) {
        mapped.manufacturer = fieldErrors.manufacturer
      }
      if (fieldErrors.model) {
        mapped.model = fieldErrors.model
      }
      if (fieldErrors.document_name) {
        mapped.documentName = fieldErrors.document_name
      }
      if (fieldErrors.version) {
        mapped.version = fieldErrors.version
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

      <FormField
        id="admin-document-file"
        label="PDF file"
        required
        error={errors.file}
      >
        <input
          id="admin-document-file"
          type="file"
          accept="application/pdf,.pdf"
          className={inputClassName}
          onChange={(event) => update('file', event.target.files?.[0] ?? null)}
        />
      </FormField>

      <div className="grid gap-4 sm:grid-cols-2">
        <FormField
          id="admin-document-manufacturer"
          label="Manufacturer"
          required
          error={errors.manufacturer}
        >
          <input
            id="admin-document-manufacturer"
            className={inputClassName}
            value={values.manufacturer}
            maxLength={150}
            onChange={(event) => update('manufacturer', event.target.value)}
          />
        </FormField>
        <FormField
          id="admin-document-model"
          label="Model"
          required
          error={errors.model}
        >
          <input
            id="admin-document-model"
            className={inputClassName}
            value={values.model}
            maxLength={150}
            onChange={(event) => update('model', event.target.value)}
          />
        </FormField>
        <FormField
          id="admin-document-name"
          label="Document name"
          required
          error={errors.documentName}
        >
          <input
            id="admin-document-name"
            className={inputClassName}
            value={values.documentName}
            maxLength={255}
            onChange={(event) => update('documentName', event.target.value)}
          />
        </FormField>
        <FormField
          id="admin-document-version"
          label="Version"
          hint="Optional, for example 2.1."
          error={errors.version}
        >
          <input
            id="admin-document-version"
            className={inputClassName}
            value={values.version}
            maxLength={100}
            onChange={(event) => update('version', event.target.value)}
          />
        </FormField>
      </div>

      <div className="flex justify-end">
        <button
          type="submit"
          disabled={isSubmitting}
          className="rounded-xl bg-sky-500 px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-sky-400 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isSubmitting ? 'Uploading...' : 'Upload document'}
        </button>
      </div>
    </form>
  )
}

export function DocumentMetadataForm({
  initial,
  isSubmitting,
  onSubmit,
  errorMessage,
}: {
  initial: DocumentMetadataFormValues
  isSubmitting: boolean
  onSubmit: (fields: DocumentUpdateRequest) => Promise<void>
  errorMessage: (error: unknown) => string
}) {
  const [values, setValues] =
    useState<DocumentMetadataFormValues>(initial)
  const [errors, setErrors] = useState<FieldErrors>({})
  const [apiError, setApiError] = useState<string | null>(null)
  const guardRef = useRef(createSubmissionGuard())

  function update<K extends keyof DocumentMetadataFormValues>(
    field: K,
    value: DocumentMetadataFormValues[K],
  ) {
    setValues((current) => ({ ...current, [field]: value }))
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!guardRef.current.begin()) {
      return
    }
    const result = validateDocumentMetadata(values)
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
      if (fieldErrors.document_name) {
        mapped.documentName = fieldErrors.document_name
      }
      if (fieldErrors.version) {
        mapped.version = fieldErrors.version
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
          id="admin-document-edit-manufacturer"
          label="Manufacturer"
          required
          error={errors.manufacturer}
        >
          <input
            id="admin-document-edit-manufacturer"
            className={inputClassName}
            value={values.manufacturer}
            maxLength={150}
            onChange={(event) => update('manufacturer', event.target.value)}
          />
        </FormField>
        <FormField
          id="admin-document-edit-model"
          label="Model"
          required
          error={errors.model}
        >
          <input
            id="admin-document-edit-model"
            className={inputClassName}
            value={values.model}
            maxLength={150}
            onChange={(event) => update('model', event.target.value)}
          />
        </FormField>
        <FormField
          id="admin-document-edit-name"
          label="Document name"
          required
          error={errors.documentName}
        >
          <input
            id="admin-document-edit-name"
            className={inputClassName}
            value={values.documentName}
            maxLength={255}
            onChange={(event) => update('documentName', event.target.value)}
          />
        </FormField>
        <FormField
          id="admin-document-edit-version"
          label="Version"
          error={errors.version}
        >
          <input
            id="admin-document-edit-version"
            className={inputClassName}
            value={values.version}
            maxLength={100}
            onChange={(event) => update('version', event.target.value)}
          />
        </FormField>
      </div>
      <div className="flex justify-end">
        <button
          type="submit"
          disabled={isSubmitting}
          className="rounded-xl bg-sky-500 px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-sky-400 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isSubmitting ? 'Saving...' : 'Save metadata'}
        </button>
      </div>
    </form>
  )
}
