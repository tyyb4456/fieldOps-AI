import './helpers/dom.ts'
import React from 'react'
import assert from 'node:assert/strict'
import test, { afterEach } from 'node:test'
import { cleanup, fireEvent, screen } from '@testing-library/react'
import type { Assignment } from '../src/features/assignments/types.ts'
import type { DocumentMetadata } from '../src/features/documents/types.ts'
import type { WorkflowRun } from '../src/features/workflows/types.ts'
import type {
  CompletionReport,
  WorkOrder,
  WorkOrderProposal,
} from '../src/features/work-orders/types.ts'
import type { Complaint } from '../src/features/complaints/types.ts'
import type { Equipment } from '../src/features/equipment/types.ts'
import { AdminAssignmentsPage } from '../src/features/admin/pages/AdminAssignmentsPage.tsx'
import { AdminComplaintDetailPage } from '../src/features/admin/pages/AdminComplaintDetailPage.tsx'
import { AdminCompletionReportDetailPage } from '../src/features/admin/pages/AdminCompletionReportDetailPage.tsx'
import { AdminDocumentDetailPage } from '../src/features/admin/pages/AdminDocumentDetailPage.tsx'
import { AdminProposalDetailPage } from '../src/features/admin/pages/AdminProposalDetailPage.tsx'
import { AdminWorkflowDetailPage } from '../src/features/admin/pages/AdminWorkflowDetailPage.tsx'
import { AdminWorkOrderDetailPage } from '../src/features/admin/pages/AdminWorkOrderDetailPage.tsx'
import {
  createTestClient,
  errorResponse,
  jsonResponse,
  requestBody,
  requestsTo,
  renderRoute,
  type RecordedRequest,
} from './helpers/customer-test-utils.tsx'

const originalConfirm = window.confirm

afterEach(() => {
  cleanup()
  window.confirm = originalConfirm
})

function page<T>(items: T[], total = items.length) {
  return { items, total, limit: Math.max(items.length, 1), offset: 0 }
}

function method(request: RecordedRequest): string {
  return request.init.method ?? 'GET'
}

function complaint(overrides: Partial<Complaint> = {}): Complaint {
  return {
    id: 'complaint-1',
    customer_id: 'customer-1',
    equipment_id: 'equipment-1',
    description: 'Inverter shuts down every morning.',
    reported_symptoms: ['Shutdown at sunrise'],
    reported_error_code: 'E-401',
    channel: 'web',
    status: 'ready_for_work_order',
    priority: 'high',
    created_at: '2026-02-01T08:00:00Z',
    updated_at: '2026-02-02T09:00:00Z',
    ...overrides,
  }
}

function equipment(overrides: Partial<Equipment> = {}): Equipment {
  return {
    id: 'equipment-1',
    customer_id: 'customer-1',
    manufacturer: 'Solis',
    model: 'S6-GR1P',
    serial_number: 'SN-1',
    equipment_type: 'inverter',
    installation_date: '2024-05-01',
    created_at: '2024-05-01T00:00:00Z',
    ...overrides,
  }
}

function workOrder(overrides: Partial<WorkOrder> = {}): WorkOrder {
  return {
    id: 'work-order-1',
    complaint_id: 'complaint-1',
    equipment_id: 'equipment-1',
    title: 'Inverter shutdown',
    description: 'Investigate morning inverter shutdowns.',
    diagnostic_checklist: ['Verify DC input'],
    priority: 'high',
    status: 'in_progress',
    created_at: '2026-02-01T08:00:00Z',
    updated_at: '2026-02-02T09:00:00Z',
    ...overrides,
  }
}

function assignment(overrides: Partial<Assignment> = {}): Assignment {
  return {
    id: 'assignment-1',
    work_order_id: 'work-order-1',
    technician_id: 'technician-1',
    assignment_status: 'accepted',
    assigned_at: '2026-02-02T09:00:00Z',
    accepted_at: '2026-02-02T10:00:00Z',
    rejected_at: null,
    ...overrides,
  }
}

function proposal(overrides: Partial<WorkOrderProposal> = {}): WorkOrderProposal {
  return {
    id: 'proposal-1',
    complaint_id: 'complaint-1',
    status: 'pending_approval',
    title: 'Inverter shutdown proposal',
    problem_description: 'Inverter shuts down every morning.',
    proposed_scope: 'Inspect DC input and error logs.',
    technical_findings: 'Loose DC connector suspected.',
    recommended_actions: ['Reseat DC connector'],
    required_skills: ['dc_systems'],
    required_parts: ['connector clip'],
    priority: 'high',
    estimated_duration_minutes: 60,
    safety_warnings: ['Isolate DC before work'],
    missing_information: [],
    generation_warnings: [],
    diagnostic_status: 'diagnosed',
    diagnostic_summary: 'Connector fault likely.',
    diagnostic_snapshot: {},
    citations: [],
    requires_escalation: false,
    escalation_reason: null,
    technician_recommendations: [],
    selected_technician_id: null,
    created_by_id: null,
    reviewed_by_id: null,
    reviewed_at: null,
    rejection_reason: null,
    resulting_work_order_id: null,
    resulting_assignment_id: null,
    created_at: '2026-02-02T09:00:00Z',
    updated_at: '2026-02-02T09:00:00Z',
    ...overrides,
  }
}

function completionReport(
  overrides: Partial<CompletionReport> = {},
): CompletionReport {
  return {
    id: 'completion-report-1',
    work_order_id: 'work-order-1',
    service_record_id: 'service-record-1',
    summary: 'Reseated the DC connector and verified output.',
    evidence_status: 'pending',
    verification_notes: null,
    submitted_at: '2026-02-04T11:00:00Z',
    verified_at: null,
    ...overrides,
  }
}

function documentMetadata(
  overrides: Partial<DocumentMetadata> = {},
): DocumentMetadata {
  return {
    id: 'document-1',
    manufacturer: 'Solis',
    model: 'S6-GR1P',
    document_name: 'Solis S6 manual',
    version: '2.1',
    original_filename: 'solis.pdf',
    content_type: 'application/pdf',
    byte_size: 2048,
    checksum_sha256: 'checksum',
    uploaded_by_id: 'admin-1',
    ingestion_status: 'failed',
    ingestion_error: 'The PDF contains no extractable text.',
    ingested_at: null,
    is_active: false,
    created_at: '2026-02-01T08:00:00Z',
    ...overrides,
  }
}

function workflowRun(overrides: Partial<WorkflowRun> = {}): WorkflowRun {
  return {
    id: 'workflow-1',
    complaint_id: 'complaint-1',
    workflow_type: 'work_order_proposal',
    status: 'failed',
    current_step: 'diagnose',
    started_at: '2026-02-03T08:00:00Z',
    finished_at: '2026-02-03T08:01:00Z',
    error_message: 'Diagnostic worker timed out.',
    ...overrides,
  }
}

test('complaint proposal generation surfaces a pending-proposal conflict', async () => {
  const requests: RecordedRequest[] = []
  const client = createTestClient((request) => {
    const path = request.url.pathname
    if (path === '/api/v1/admin/complaints/complaint-1') {
      return jsonResponse(complaint())
    }
    if (path === '/api/v1/admin/complaints/complaint-1/history') {
      return jsonResponse(page([]))
    }
    if (path === '/api/v1/admin/equipment/equipment-1') {
      return jsonResponse(equipment())
    }
    if (path === '/api/v1/admin/work-order-proposals') {
      return jsonResponse(page([]))
    }
    if (path === '/api/v1/admin/work-orders') {
      return jsonResponse(page([]))
    }
    if (
      path === '/api/v1/admin/complaints/complaint-1/work-order-proposals' &&
      method(request) === 'POST'
    ) {
      return errorResponse(
        409,
        'proposal_already_pending',
        'A proposal is already pending.',
      )
    }
    return errorResponse(404, 'not_found', 'Unexpected request')
  }, requests)

  renderRoute(client, <AdminComplaintDetailPage />, {
    initialEntry: '/admin/complaints/complaint-1',
    path: '/admin/complaints/:complaintId',
  })

  fireEvent.click(await screen.findByRole('button', { name: 'Generate proposal' }))

  assert.ok(
    await screen.findByText(
      'A work-order proposal is already pending review for this complaint.',
    ),
  )
  assert.equal(
    requestsTo(
      requests,
      '/api/v1/admin/complaints/complaint-1/work-order-proposals',
    ).length,
    1,
  )
})

test('work-order lifecycle errors are mapped and do not mutate local state', async () => {
  const requests: RecordedRequest[] = []
  const client = createTestClient((request) => {
    const path = request.url.pathname
    if (path === '/api/v1/admin/work-orders/work-order-1') {
      return jsonResponse(workOrder())
    }
    if (path === '/api/v1/admin/assignments') {
      return jsonResponse(page([]))
    }
    if (path === '/api/v1/admin/work-orders/work-order-1/completion-reports') {
      return jsonResponse(page([]))
    }
    if (path === '/api/v1/admin/service-records') {
      return jsonResponse(page([]))
    }
    if (path === '/api/v1/admin/technicians') {
      return jsonResponse(page([]))
    }
    if (
      path === '/api/v1/admin/work-orders/work-order-1/status' &&
      method(request) === 'POST'
    ) {
      return errorResponse(
        409,
        'invalid_status_transition',
        'Transition rejected.',
      )
    }
    return errorResponse(404, 'not_found', 'Unexpected request')
  }, requests)

  renderRoute(client, <AdminWorkOrderDetailPage />, {
    initialEntry: '/admin/work-orders/work-order-1',
    path: '/admin/work-orders/:workOrderId',
  })

  fireEvent.click(
    await screen.findByRole('button', { name: 'Move to Awaiting verification' }),
  )

  assert.ok(
    await screen.findByText(
      'The work order cannot be moved to that state right now.',
    ),
  )
  assert.ok(screen.getByText('In progress'))
  assert.equal(
    requestsTo(
      requests,
      '/api/v1/admin/work-orders/work-order-1/status',
    ).length,
    1,
  )
})

test('administrator can retry a withdraw after an assignment conflict', async () => {
  const requests: RecordedRequest[] = []
  let withdrawn = false
  let withdrawAttempts = 0
  const client = createTestClient((request) => {
    const path = request.url.pathname
    if (
      path === '/api/v1/admin/assignments' &&
      method(request) === 'GET'
    ) {
      return jsonResponse(
        page([
          assignment({
            assignment_status: withdrawn ? 'withdrawn' : 'accepted',
          }),
        ]),
      )
    }
    if (
      path === '/api/v1/admin/assignments/assignment-1/withdraw' &&
      method(request) === 'POST'
    ) {
      withdrawAttempts += 1
      if (withdrawAttempts === 1) {
        return errorResponse(
          409,
          'assignment_conflict',
          'Assignment is being updated.',
        )
      }
      withdrawn = true
      return jsonResponse(assignment({ assignment_status: 'withdrawn' }))
    }
    return errorResponse(404, 'not_found', 'Unexpected request')
  }, requests)

  window.confirm = () => true

  renderRoute(client, <AdminAssignmentsPage />, {
    initialEntry: '/admin/assignments',
    path: '/admin/assignments',
  })

  const withdrawButton = await screen.findByRole('button', {
    name: 'Withdraw assignment',
  })
  fireEvent.click(withdrawButton)

  assert.ok(
    await screen.findByText('This work order already has an active assignment.'),
  )

  fireEvent.click(
    screen.getByRole('button', { name: 'Withdraw assignment' }),
  )

  assert.ok(await screen.findByText('Assignment withdrawn.'))
  assert.equal(
    requestsTo(
      requests,
      '/api/v1/admin/assignments/assignment-1/withdraw',
    ).length,
    2,
  )
})

test('proposal decisions handle stale snapshots and validate rejection reasons', async () => {
  const requests: RecordedRequest[] = []
  let current = proposal()
  const client = createTestClient((request) => {
    const path = request.url.pathname
    if (
      path === '/api/v1/admin/work-order-proposals/proposal-1' &&
      method(request) === 'GET'
    ) {
      return jsonResponse(current)
    }
    if (
      path === '/api/v1/admin/work-order-proposals/proposal-1/approve' &&
      method(request) === 'POST'
    ) {
      return errorResponse(
        409,
        'proposal_stale',
        'The complaint changed since generation.',
      )
    }
    if (
      path === '/api/v1/admin/work-order-proposals/proposal-1/reject' &&
      method(request) === 'POST'
    ) {
      const body = requestBody(request) as { reason: string }
      current = proposal({
        status: 'rejected',
        rejection_reason: body.reason,
        reviewed_at: '2026-02-04T08:00:00Z',
      })
      return jsonResponse(current)
    }
    return errorResponse(404, 'not_found', 'Unexpected request')
  }, requests)

  renderRoute(client, <AdminProposalDetailPage />, {
    initialEntry: '/admin/proposals/proposal-1',
    path: '/admin/proposals/:proposalId',
  })

  fireEvent.click(await screen.findByRole('button', { name: 'Approve proposal' }))

  assert.ok(
    await screen.findByText(
      'This proposal is stale. Generate a new proposal before deciding.',
    ),
  )

  fireEvent.click(screen.getByRole('button', { name: 'Reject' }))
  fireEvent.click(screen.getByRole('button', { name: 'Reject proposal' }))

  assert.ok(
    await screen.findByText('Enter a rejection reason of at least 3 characters.'),
  )
  assert.equal(
    requestsTo(
      requests,
      '/api/v1/admin/work-order-proposals/proposal-1/reject',
    ).length,
    0,
  )

  fireEvent.change(screen.getByLabelText(/Rejection reason/), {
    target: { value: '  Duplicate proposal.  ' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Reject proposal' }))

  assert.ok(await screen.findByText('Proposal rejected.'))
  assert.ok(await screen.findByText('Duplicate proposal.'))
  const rejectRequests = requestsTo(
    requests,
    '/api/v1/admin/work-order-proposals/proposal-1/reject',
  )
  assert.equal(rejectRequests.length, 1)
  assert.deepEqual(requestBody(rejectRequests[0]), {
    reason: 'Duplicate proposal.',
  })
})

test('rejecting completion evidence requires notes before submitting', async () => {
  const requests: RecordedRequest[] = []
  let current = completionReport()
  const client = createTestClient((request) => {
    const path = request.url.pathname
    if (
      path === '/api/v1/admin/completion-reports/completion-report-1' &&
      method(request) === 'GET'
    ) {
      return jsonResponse(current)
    }
    if (
      path === '/api/v1/admin/completion-reports/completion-report-1' &&
      method(request) === 'PATCH'
    ) {
      const body = requestBody(request) as {
        evidence_status: CompletionReport['evidence_status']
        verification_notes: string | null
      }
      current = completionReport({
        evidence_status: body.evidence_status,
        verification_notes: body.verification_notes,
      })
      return jsonResponse(current)
    }
    return errorResponse(404, 'not_found', 'Unexpected request')
  }, requests)

  renderRoute(client, <AdminCompletionReportDetailPage />, {
    initialEntry: '/admin/completion-reports/completion-report-1',
    path: '/admin/completion-reports/:completionReportId',
  })

  fireEvent.click(await screen.findByRole('button', { name: 'Reject evidence' }))

  assert.ok(
    await screen.findByText(
      'Add notes explaining why this evidence is rejected.',
    ),
  )
  assert.equal(
    requestsTo(
      requests,
      '/api/v1/admin/completion-reports/completion-report-1',
    ).filter((request) => method(request) === 'PATCH').length,
    0,
  )

  fireEvent.change(screen.getByLabelText('Verification notes'), {
    target: { value: 'Photos do not show the completed repair.' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Reject evidence' }))

  assert.ok(
    await screen.findByText(
      'Evidence rejected. The technician can revise the report.',
    ),
  )
  const patchRequests = requestsTo(
    requests,
    '/api/v1/admin/completion-reports/completion-report-1',
  ).filter((request) => method(request) === 'PATCH')
  assert.equal(patchRequests.length, 1)
  assert.deepEqual(requestBody(patchRequests[0]), {
    evidence_status: 'rejected',
    verification_notes: 'Photos do not show the completed repair.',
  })
})

test('verified completion evidence is read-only', async () => {
  const requests: RecordedRequest[] = []
  const client = createTestClient(
    (request) =>
      request.url.pathname ===
      '/api/v1/admin/completion-reports/completion-report-1'
        ? jsonResponse(
            completionReport({
              evidence_status: 'verified',
              verification_notes: 'Evidence matches the service record.',
              verified_at: '2026-02-05T08:00:00Z',
            }),
          )
        : errorResponse(404, 'not_found', 'Unexpected request'),
    requests,
  )

  renderRoute(client, <AdminCompletionReportDetailPage />, {
    initialEntry: '/admin/completion-reports/completion-report-1',
    path: '/admin/completion-reports/:completionReportId',
  })

  assert.ok(
    await screen.findByText('This evidence has been verified and is immutable.'),
  )
  assert.equal(
    screen.queryByRole('button', { name: 'Verify evidence' }),
    null,
  )
  assert.equal(
    screen.queryByRole('button', { name: 'Reject evidence' }),
    null,
  )
})

test('failed document ingestion shows the error and can be re-ingested', async () => {
  const requests: RecordedRequest[] = []
  let current = documentMetadata()
  const client = createTestClient((request) => {
    const path = request.url.pathname
    if (
      path === '/api/v1/admin/documents/document-1' &&
      method(request) === 'GET'
    ) {
      return jsonResponse(current)
    }
    if (path === '/api/v1/admin/documents/document-1/chunks') {
      return jsonResponse(page([]))
    }
    if (
      path === '/api/v1/admin/documents/document-1/ingest' &&
      method(request) === 'POST'
    ) {
      current = documentMetadata({
        ingestion_status: 'processing',
        ingestion_error: null,
      })
      return jsonResponse(current)
    }
    return errorResponse(404, 'not_found', 'Unexpected request')
  }, requests)

  renderRoute(client, <AdminDocumentDetailPage />, {
    initialEntry: '/admin/documents/document-1',
    path: '/admin/documents/:documentId',
  })

  assert.ok(
    await screen.findByText('The PDF contains no extractable text.'),
  )
  assert.ok(
    screen.getByText(
      'Chunks are available after ingestion completes successfully.',
    ),
  )
  assert.equal(screen.queryByRole('button', { name: 'Activate' }), null)

  fireEvent.click(screen.getByRole('button', { name: 'Re-ingest' }))

  assert.ok(await screen.findByText('Document queued for re-ingestion.'))
  assert.equal(
    requestsTo(
      requests,
      '/api/v1/admin/documents/document-1/ingest',
    ).length,
    1,
  )
})

test('workflow detail recovers from a load failure and shows failed-run details', async () => {
  const requests: RecordedRequest[] = []
  let attempts = 0
  const client = createTestClient((request) => {
    if (request.url.pathname !== '/api/v1/admin/workflow-runs/workflow-1') {
      return errorResponse(404, 'not_found', 'Unexpected request')
    }
    attempts += 1
    if (attempts === 1) {
      return errorResponse(503, 'service_unavailable', 'Try later.')
    }
    return jsonResponse(workflowRun())
  }, requests)

  renderRoute(client, <AdminWorkflowDetailPage />, {
    initialEntry: '/admin/workflows/workflow-1',
    path: '/admin/workflows/:workflowId',
  })

  assert.ok(await screen.findByText('Something went wrong'))
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }))

  assert.ok(await screen.findByText('Diagnostic worker timed out.'))
  assert.ok(
    screen.getByText(
      /This view is read-only; failed runs require investigation before retrying the underlying action\./,
    ),
  )
  assert.equal(
    requestsTo(requests, '/api/v1/admin/workflow-runs/workflow-1').length,
    2,
  )
})
