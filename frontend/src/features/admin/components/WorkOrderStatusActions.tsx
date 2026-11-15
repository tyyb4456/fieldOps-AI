import { useState } from 'react'
import { FormError } from '../../../components/Feedback'
import type { WorkOrderStatus } from '../../../lib/api/types'
import { workOrderStatusLabel } from '../../technicians/labels'

const ADMIN_TRANSITIONS: Record<WorkOrderStatus, readonly WorkOrderStatus[]> = {
  draft: ['validated', 'cancelled'],
  validated: ['awaiting_assignment', 'cancelled'],
  awaiting_assignment: ['escalated', 'cancelled'],
  assigned: ['escalated', 'cancelled'],
  accepted: ['escalated', 'cancelled'],
  in_progress: ['pending_verification', 'escalated', 'cancelled'],
  awaiting_parts: ['in_progress', 'escalated', 'cancelled'],
  pending_verification: ['completed', 'in_progress', 'escalated'],
  escalated: ['awaiting_assignment', 'cancelled'],
  completed: [],
  cancelled: [],
}

export function AdminWorkOrderStatusActions({
  status,
  isSubmitting,
  onTransition,
  error,
}: {
  status: WorkOrderStatus
  isSubmitting: boolean
  onTransition: (status: WorkOrderStatus) => Promise<void>
  error: string | null
}) {
  const [pendingStatus, setPendingStatus] = useState<WorkOrderStatus | null>(
    null,
  )
  const transitions = ADMIN_TRANSITIONS[status]

  async function transition(target: WorkOrderStatus) {
    if (pendingStatus !== null) {
      return
    }
    if (
      (target === 'cancelled' || target === 'escalated') &&
      !window.confirm(
        `Move this work order to ${workOrderStatusLabel(target).toLowerCase()}?`,
      )
    ) {
      return
    }
    setPendingStatus(target)
    try {
      await onTransition(target)
    } finally {
      setPendingStatus(null)
    }
  }

  return (
    <div className="grid gap-3">
      {transitions.length === 0 ? (
        <p className="text-sm text-slate-400">
          This work order is in a terminal state.
        </p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {transitions.map((target) => (
            <button
              key={target}
              type="button"
              disabled={isSubmitting || pendingStatus !== null}
              onClick={() => void transition(target)}
              className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-medium text-slate-200 transition hover:border-sky-500/60 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
            >
              {pendingStatus === target
                ? 'Updating...'
                : `Move to ${workOrderStatusLabel(target)}`}
            </button>
          ))}
        </div>
      )}
      <FormError message={error} />
    </div>
  )
}
