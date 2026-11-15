import { useRef, useState, type FormEvent } from 'react'
import { FormError, InlineWarning } from '../../../components/Feedback'
import {
  FormField,
  inputClassName,
} from '../../../components/FormField'
import type { TechnicianSummary } from '../../assignments/types'
import { createSubmissionGuard } from '../../../lib/forms/submission-guard'
import { validateAssignmentTechnician } from '../validation'

export function AssignmentOfferForm({
  technicians,
  hasActiveAssignment,
  isSubmitting,
  onSubmit,
  error,
}: {
  technicians: readonly TechnicianSummary[]
  hasActiveAssignment: boolean
  isSubmitting: boolean
  onSubmit: (technicianId: string) => Promise<void>
  error: string | null
}) {
  const [technicianId, setTechnicianId] = useState(
    technicians[0]?.id ?? '',
  )
  const [fieldError, setFieldError] = useState<string | null>(null)
  const guardRef = useRef(createSubmissionGuard())

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!guardRef.current.begin()) {
      return
    }
    const result = validateAssignmentTechnician(technicianId)
    setFieldError(result.errors.technicianId ?? null)
    if (!result.isValid || result.payload === null) {
      guardRef.current.end()
      return
    }
    try {
      await onSubmit(result.payload)
    } finally {
      guardRef.current.end()
    }
  }

  if (technicians.length === 0) {
    return (
      <InlineWarning>
        No available technicians are currently eligible for assignment.
      </InlineWarning>
    )
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="grid gap-4">
      <FormError message={error} />
      <FormField
        id="admin-assignment-technician"
        label="Technician"
        hint={
          hasActiveAssignment
            ? 'Reassigning withdraws the current active offer or accepted assignment.'
            : 'Choose an available technician to offer this work order.'
        }
        error={fieldError ?? undefined}
      >
        <select
          id="admin-assignment-technician"
          className={inputClassName}
          value={technicianId}
          onChange={(event) => setTechnicianId(event.target.value)}
        >
          {technicians.map((technician) => (
            <option key={technician.id} value={technician.id}>
              {technician.full_name}
              {technician.service_area
                ? ` - ${technician.service_area}`
                : ''}
            </option>
          ))}
        </select>
      </FormField>
      <div className="flex justify-end">
        <button
          type="submit"
          disabled={isSubmitting}
          className="rounded-xl bg-sky-500 px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-sky-400 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isSubmitting
            ? 'Saving...'
            : hasActiveAssignment
              ? 'Reassign work order'
              : 'Offer assignment'}
        </button>
      </div>
    </form>
  )
}
