import { useState } from 'react'
import { FormError } from '../../../components/Feedback'
import { useApiClient } from '../../../lib/api/api-client-context'
import type { WorkOrderStatus } from '../../../lib/api/types'
import { updateWorkOrderStatus } from '../../work-orders/api'
import type { WorkOrder } from '../../work-orders/types'
import { workOrderStatusErrorMessage } from '../errors'
import type { TechnicianLifecycle } from '../lifecycle'

interface StatusAction {
  label: string
  busyLabel: string
  target: WorkOrderStatus
  confirmMessage?: string
}

export function WorkOrderStatusActions({
  workOrderId,
  lifecycle,
  onUpdated,
}: {
  workOrderId: string
  lifecycle: TechnicianLifecycle
  onUpdated: (workOrder: WorkOrder) => void
}) {
  const apiClient = useApiClient()
  const [pendingTarget, setPendingTarget] = useState<WorkOrderStatus | null>(
    null,
  )
  const [error, setError] = useState<string | null>(null)

  const actions: StatusAction[] = []

  if (lifecycle.canStartWork) {
    actions.push({
      label: 'Start work',
      busyLabel: 'Starting...',
      target: 'in_progress',
    })
  }
  if (lifecycle.canMarkAwaitingParts) {
    actions.push({
      label: 'Mark awaiting parts',
      busyLabel: 'Updating...',
      target: 'awaiting_parts',
    })
  }
  if (lifecycle.canResumeWork) {
    actions.push({
      label: 'Resume work',
      busyLabel: 'Resuming...',
      target: 'in_progress',
    })
  }
  if (lifecycle.canSubmitForVerification) {
    actions.push({
      label: 'Submit for verification',
      busyLabel: 'Submitting...',
      target: 'pending_verification',
      confirmMessage:
        'Submit this work order for verification? You will not be able to add service records afterwards.',
    })
  }
  if (lifecycle.canEscalate) {
    actions.push({
      label: 'Escalate work order',
      busyLabel: 'Escalating...',
      target: 'escalated',
      confirmMessage:
        'Escalate this work order to the service team? Technician actions will be disabled.',
    })
  }

  if (actions.length === 0) {
    return null
  }

  async function run(action: StatusAction) {
    if (pendingTarget !== null) {
      return
    }

    if (action.confirmMessage && !window.confirm(action.confirmMessage)) {
      return
    }

    setPendingTarget(action.target)
    setError(null)

    try {
      const updated = await updateWorkOrderStatus(
        apiClient,
        workOrderId,
        action.target,
      )
      onUpdated(updated)
    } catch (caught) {
      setError(workOrderStatusErrorMessage(caught))
    } finally {
      setPendingTarget(null)
    }
  }

  return (
    <div className="grid gap-2">
      <div className="flex flex-wrap gap-2">
        {actions.map((action) => (
          <button
            key={action.label}
            type="button"
            onClick={() => void run(action)}
            disabled={pendingTarget !== null}
            className={
              action.target === 'escalated'
                ? 'rounded-xl border border-rose-500/40 px-4 py-2.5 text-sm font-medium text-rose-200 transition hover:bg-rose-500/10 disabled:cursor-not-allowed disabled:opacity-60'
                : 'rounded-xl bg-sky-500 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-sky-400 disabled:cursor-not-allowed disabled:opacity-60'
            }
          >
            {pendingTarget === action.target ? action.busyLabel : action.label}
          </button>
        ))}
      </div>
      <FormError message={error} />
    </div>
  )
}
