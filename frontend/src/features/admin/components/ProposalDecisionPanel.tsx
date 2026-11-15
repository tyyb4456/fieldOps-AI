import { useRef, useState, type FormEvent } from 'react'
import { FormError, InlineWarning } from '../../../components/Feedback'
import {
  FormField,
  inputClassName,
} from '../../../components/FormField'
import { createSubmissionGuard } from '../../../lib/forms/submission-guard'
import type { WorkOrderProposal } from '../../work-orders/types'
import { validateProposalReject } from '../validation'

type DecisionMode = 'approve' | 'reject'

export function ProposalDecisionPanel({
  proposal,
  isSubmitting,
  onApprove,
  onReject,
  error,
}: {
  proposal: WorkOrderProposal
  isSubmitting: boolean
  onApprove: (technicianId: string | null) => Promise<void>
  onReject: (reason: string) => Promise<void>
  error: string | null
}) {
  const eligible = proposal.technician_recommendations.filter(
    (recommendation) => recommendation.eligible,
  )
  const [mode, setMode] = useState<DecisionMode>('approve')
  const [technicianId, setTechnicianId] = useState('')
  const [reason, setReason] = useState('')
  const [fieldError, setFieldError] = useState<string | null>(null)
  const guardRef = useRef(createSubmissionGuard())

  async function handleApprove() {
    if (!guardRef.current.begin()) {
      return
    }
    setFieldError(null)
    try {
      await onApprove(technicianId || null)
    } finally {
      guardRef.current.end()
    }
  }

  async function handleReject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!guardRef.current.begin()) {
      return
    }
    const result = validateProposalReject(reason)
    setFieldError(result.errors.reason ?? null)
    if (!result.isValid || result.payload === null) {
      guardRef.current.end()
      return
    }
    try {
      await onReject(result.payload)
    } finally {
      guardRef.current.end()
    }
  }

  return (
    <div className="grid gap-4">
      <FormError message={error} />

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => {
            setMode('approve')
            setFieldError(null)
          }}
          className={`rounded-xl px-4 py-2 text-sm font-semibold transition ${
            mode === 'approve'
              ? 'bg-sky-500 text-slate-950'
              : 'border border-slate-700 text-slate-200 hover:border-slate-500'
          }`}
        >
          Approve
        </button>
        <button
          type="button"
          onClick={() => {
            setMode('reject')
            setFieldError(null)
          }}
          className={`rounded-xl px-4 py-2 text-sm font-semibold transition ${
            mode === 'reject'
              ? 'bg-rose-500 text-slate-950'
              : 'border border-slate-700 text-slate-200 hover:border-slate-500'
          }`}
        >
          Reject
        </button>
      </div>

      {mode === 'approve' ? (
        <div className="grid gap-4">
          <FormField
            id="admin-proposal-technician"
            label="Assign technician after approval"
            hint="Optional. Approval creates the work order; selecting a technician also offers the assignment."
          >
            <select
              id="admin-proposal-technician"
              className={inputClassName}
              value={technicianId}
              onChange={(event) => setTechnicianId(event.target.value)}
            >
              <option value="">No technician yet</option>
              {eligible.map((recommendation) => (
                <option
                  key={recommendation.technician_id}
                  value={recommendation.technician_id}
                >
                  {recommendation.full_name} (rank {recommendation.rank})
                </option>
              ))}
            </select>
          </FormField>

          {eligible.length === 0 ? (
            <InlineWarning>
              No eligible technician recommendations are attached to this
              proposal. You can approve it and assign a technician later.
            </InlineWarning>
          ) : null}

          <div className="flex justify-end">
            <button
              type="button"
              onClick={() => void handleApprove()}
              disabled={isSubmitting}
              className="rounded-xl bg-emerald-500 px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isSubmitting ? 'Approving...' : 'Approve proposal'}
            </button>
          </div>
        </div>
      ) : (
        <form onSubmit={handleReject} noValidate className="grid gap-4">
          <FormField
            id="admin-proposal-reason"
            label="Rejection reason"
            required
            error={fieldError ?? undefined}
          >
            <textarea
              id="admin-proposal-reason"
              className={`${inputClassName} min-h-28 resize-y`}
              value={reason}
              maxLength={2000}
              required
              onChange={(event) => setReason(event.target.value)}
            />
          </FormField>
          <div className="flex justify-end">
            <button
              type="submit"
              disabled={isSubmitting}
              className="rounded-xl bg-rose-500 px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-rose-400 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isSubmitting ? 'Rejecting...' : 'Reject proposal'}
            </button>
          </div>
        </form>
      )}
    </div>
  )
}
