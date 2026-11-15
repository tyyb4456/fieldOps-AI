import assert from 'node:assert/strict'
import test from 'node:test'
import type { WorkOrderStatus } from '../src/lib/api/types.ts'
import {
  canModifyCompletionReports,
  canModifyServiceRecords,
  getTechnicianLifecycle,
} from '../src/features/technicians/lifecycle.ts'

function lifecycle(
  workOrderStatus: WorkOrderStatus,
  overrides: Partial<Parameters<typeof getTechnicianLifecycle>[0]> = {},
) {
  return getTechnicianLifecycle({
    workOrderStatus,
    hasOfferedAssignment: false,
    hasAcceptedAssignment: true,
    hasServiceRecord: false,
    hasEligibleServiceRecord: false,
    ...overrides,
  })
}

test('offered assignments only unlock accept and reject while assigned', () => {
  const offered = lifecycle('assigned', { hasOfferedAssignment: true })

  assert.equal(offered.canAccept, true)
  assert.equal(offered.canReject, true)
  assert.equal(offered.canStartWork, false)
  assert.equal(offered.canCreateServiceRecord, false)
  assert.equal(offered.canCreateCompletionReport, false)

  const escalatedOffer = lifecycle('escalated', {
    hasOfferedAssignment: true,
  })

  assert.equal(escalatedOffer.canAccept, false)
  assert.equal(escalatedOffer.canReject, false)
})

test('technician work-order actions match the backend transition map', () => {
  const accepted = lifecycle('accepted')
  assert.equal(accepted.canStartWork, true)
  assert.equal(accepted.canMarkAwaitingParts, false)
  assert.equal(accepted.canSubmitForVerification, false)
  assert.equal(accepted.canEscalate, false)
  assert.equal(accepted.canResumeWork, false)

  const inProgress = lifecycle('in_progress')
  assert.equal(inProgress.canStartWork, false)
  assert.equal(inProgress.canMarkAwaitingParts, true)
  assert.equal(inProgress.canSubmitForVerification, false)
  assert.equal(inProgress.canEscalate, true)
  assert.equal(inProgress.canResumeWork, false)

  const withRecord = lifecycle('in_progress', { hasServiceRecord: true })
  assert.equal(withRecord.canSubmitForVerification, true)

  const awaitingParts = lifecycle('awaiting_parts')
  assert.equal(awaitingParts.canResumeWork, true)
  assert.equal(awaitingParts.canSubmitForVerification, false)
  assert.equal(awaitingParts.canEscalate, false)

  for (const status of [
    'pending_verification',
    'escalated',
    'completed',
    'cancelled',
  ] as const) {
    const state = lifecycle(status)
    assert.equal(state.canStartWork, false)
    assert.equal(state.canMarkAwaitingParts, false)
    assert.equal(state.canSubmitForVerification, false)
    assert.equal(state.canEscalate, false)
    assert.equal(state.canResumeWork, false)
  }
})

test('technicians have no completion action in any lifecycle state', () => {
  for (const status of [
    'assigned',
    'accepted',
    'in_progress',
    'awaiting_parts',
    'pending_verification',
    'escalated',
    'completed',
    'cancelled',
  ] as const) {
    const state = lifecycle(status, {
      hasOfferedAssignment: status === 'assigned',
      hasServiceRecord: true,
      hasEligibleServiceRecord: true,
    })

    assert.equal('canCompleteWorkOrder' in state, false)
    assert.equal('canMarkCompleted' in state, false)
  }
})

test('service records lock once the work order leaves active service', () => {
  assert.equal(canModifyServiceRecords('accepted'), true)
  assert.equal(canModifyServiceRecords('in_progress'), true)
  assert.equal(canModifyServiceRecords('awaiting_parts'), true)

  for (const status of [
    'pending_verification',
    'escalated',
    'completed',
    'cancelled',
    'assigned',
  ] as const) {
    assert.equal(canModifyServiceRecords(status), false)
  }
})

test('completion reports are only editable in reportable work-order states', () => {
  assert.equal(canModifyCompletionReports('accepted'), true)
  assert.equal(canModifyCompletionReports('in_progress'), true)
  assert.equal(canModifyCompletionReports('awaiting_parts'), true)
  assert.equal(canModifyCompletionReports('pending_verification'), true)

  for (const status of [
    'assigned',
    'escalated',
    'completed',
    'cancelled',
  ] as const) {
    assert.equal(canModifyCompletionReports(status), false)
  }
})

test('an accepted assignment is required for technician actions', () => {
  const unavailable = lifecycle('in_progress', {
    hasAcceptedAssignment: false,
  })

  assert.equal(unavailable.phase, 'unavailable')
  assert.equal(unavailable.canStartWork, false)
  assert.equal(unavailable.canMarkAwaitingParts, false)
  assert.equal(unavailable.canSubmitForVerification, false)
  assert.equal(unavailable.canEscalate, false)
  assert.equal(unavailable.canResumeWork, false)
  assert.equal(unavailable.canCreateServiceRecord, false)
  assert.equal(unavailable.canUpdateServiceRecords, false)
  assert.equal(unavailable.canCreateCompletionReport, false)
})
