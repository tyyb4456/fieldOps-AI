import { useRef, useState } from 'react'
import { FormError } from '../../../components/Feedback'
import {
  FormField,
  inputClassName,
} from '../../../components/FormField'
import { createSubmissionGuard } from '../../../lib/forms/submission-guard'
import type { CompletionReportUpdateRequest } from '../../work-orders/types'
import {
  validateCompletionVerification,
  type VerificationAction,
} from '../validation'

export function CompletionVerificationForm({
  initialNotes,
  canReject = true,
  isSubmitting,
  onSubmit,
  error,
}: {
  initialNotes: string
  canReject?: boolean
  isSubmitting: boolean
  onSubmit: (payload: CompletionReportUpdateRequest) => Promise<void>
  error: string | null
}) {
  const [notes, setNotes] = useState(initialNotes)
  const [fieldError, setFieldError] = useState<string | null>(null)
  const [pendingAction, setPendingAction] =
    useState<VerificationAction | null>(null)
  const guardRef = useRef(createSubmissionGuard())

  async function submit(action: VerificationAction) {
    if (!guardRef.current.begin()) {
      return
    }
    const result = validateCompletionVerification(action, notes)
    setFieldError(result.errors.verificationNotes ?? null)
    if (!result.isValid || result.payload === null) {
      guardRef.current.end()
      return
    }
    setPendingAction(action)
    try {
      await onSubmit(result.payload)
    } finally {
      setPendingAction(null)
      guardRef.current.end()
    }
  }

  return (
    <div className="grid gap-4">
      <FormError message={error} />
      <FormField
        id="admin-completion-notes"
        label="Verification notes"
        hint="Required when rejecting evidence; optional when verifying."
        error={fieldError ?? undefined}
      >
        <textarea
          id="admin-completion-notes"
          className={`${inputClassName} min-h-28 resize-y`}
          value={notes}
          maxLength={10000}
          onChange={(event) => setNotes(event.target.value)}
        />
      </FormField>
      <div className="flex flex-wrap justify-end gap-2">
        {canReject ? (
          <button
            type="button"
            onClick={() => void submit('rejected')}
            disabled={isSubmitting}
            className="rounded-xl border border-rose-500/50 px-5 py-2.5 text-sm font-semibold text-rose-200 transition hover:bg-rose-500/10 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {pendingAction === 'rejected' ? 'Rejecting...' : 'Reject evidence'}
          </button>
        ) : null}
        <button
          type="button"
          onClick={() => void submit('verified')}
          disabled={isSubmitting}
          className="rounded-xl bg-emerald-500 px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {pendingAction === 'verified' ? 'Verifying...' : 'Verify evidence'}
        </button>
      </div>
    </div>
  )
}
