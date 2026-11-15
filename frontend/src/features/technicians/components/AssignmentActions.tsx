import { useState } from 'react'
import { FormError } from '../../../components/Feedback'
import { useApiClient } from '../../../lib/api/api-client-context'
import {
  acceptAssignment,
  rejectAssignment,
} from '../../assignments/api'
import type { Assignment } from '../../assignments/types'
import { assignmentActionErrorMessage } from '../errors'

export type AssignmentAction = 'accepted' | 'rejected'

export function AssignmentActions({
  assignment,
  onUpdated,
}: {
  assignment: Assignment
  onUpdated: (assignment: Assignment, action: AssignmentAction) => void
}) {
  const apiClient = useApiClient()
  const [pendingAction, setPendingAction] = useState<
    AssignmentAction | null
  >(null)
  const [error, setError] = useState<string | null>(null)

  if (assignment.assignment_status !== 'offered') {
    return null
  }

  async function act(action: AssignmentAction) {
    if (pendingAction !== null) {
      return
    }

    if (
      action === 'rejected' &&
      !window.confirm(
        'Reject this assignment? The service team will need to assign the work order again.',
      )
    ) {
      return
    }

    setPendingAction(action)
    setError(null)

    try {
      const updated =
        action === 'accepted'
          ? await acceptAssignment(apiClient, assignment.id)
          : await rejectAssignment(apiClient, assignment.id)
      onUpdated(updated, action)
    } catch (caught) {
      setError(assignmentActionErrorMessage(caught))
    } finally {
      setPendingAction(null)
    }
  }

  return (
    <div className="grid gap-2">
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => void act('accepted')}
          disabled={pendingAction !== null}
          className="rounded-xl bg-emerald-500 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {pendingAction === 'accepted' ? 'Accepting...' : 'Accept assignment'}
        </button>
        <button
          type="button"
          onClick={() => void act('rejected')}
          disabled={pendingAction !== null}
          className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-medium text-slate-200 transition hover:border-rose-400/60 hover:text-rose-200 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {pendingAction === 'rejected' ? 'Rejecting...' : 'Reject assignment'}
        </button>
      </div>
      <FormError message={error} />
    </div>
  )
}
