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
import type { CustomerProfile, CustomerUpdateRequest } from '../types'
import {
  validateCustomerProfileForm,
  type CustomerProfileFormValues,
} from '../validation'

export function ProfileForm({
  profile,
  onSubmit,
}: {
  profile: CustomerProfile
  onSubmit: (payload: CustomerUpdateRequest) => Promise<void>
}) {
  const [values, setValues] = useState<CustomerProfileFormValues>({
    address: profile.address ?? '',
    preferredLanguage: profile.preferred_language ?? '',
  })
  const [errors, setErrors] = useState<FieldErrors>({})
  const [apiError, setApiError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const guardRef = useRef(createSubmissionGuard())

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (!guardRef.current.begin()) {
      return
    }

    const result = validateCustomerProfileForm(values)
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
      if (fieldErrors.address) {
        mapped.address = fieldErrors.address
      }
      if (fieldErrors.preferred_language) {
        mapped.preferredLanguage = fieldErrors.preferred_language
      }
      setErrors(mapped)
      setApiError(
        Object.keys(fieldErrors).length > 0
          ? 'Please correct the highlighted fields.'
          : apiErrorMessage(caught, 'Unable to update your profile.'),
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
        <FormField id="profile-address" label="Service address">
          <textarea
            id="profile-address"
            className={`${inputClassName} min-h-24 resize-y`}
            value={values.address}
            maxLength={2000}
            aria-invalid={errors.address ? true : undefined}
            aria-describedby={
              errors.address ? 'profile-address-error' : undefined
            }
            onChange={(event) =>
              setValues((current) => ({
                ...current,
                address: event.target.value,
              }))
            }
          />
        </FormField>

        <FormField
          id="profile-language"
          label="Preferred language"
          hint="Use a short language code such as en, ur, or ar."
          error={errors.preferredLanguage}
        >
          <input
            id="profile-language"
            className={inputClassName}
            value={values.preferredLanguage}
            maxLength={30}
            aria-invalid={errors.preferredLanguage ? true : undefined}
            aria-describedby={
              errors.preferredLanguage
                ? 'profile-language-error'
                : 'profile-language-hint'
            }
            onChange={(event) =>
              setValues((current) => ({
                ...current,
                preferredLanguage: event.target.value,
              }))
            }
          />
        </FormField>
      </div>

      <div className="flex justify-end">
        <button
          type="submit"
          disabled={isSubmitting}
          className="rounded-xl bg-sky-500 px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-sky-400 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isSubmitting ? 'Saving...' : 'Save profile'}
        </button>
      </div>
    </form>
  )
}
