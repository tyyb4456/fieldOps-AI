import './helpers/dom.ts'
import React from 'react'
import assert from 'node:assert/strict'
import test, { afterEach } from 'node:test'
import { cleanup, fireEvent, screen } from '@testing-library/react'
import type { Assignment } from '../src/features/assignments/types.ts'
import type { DocumentMetadata } from '../src/features/documents/types.ts'
import type { Equipment } from '../src/features/equipment/types.ts'
import type {
  CompletionReport,
  WorkOrder,
  WorkOrderProposal,
} from '../src/features/work-orders/types.ts'
import type { Complaint } from '../src/features/complaints/types.ts'
import type { WorkflowRunAccepted } from '../src/features/workflows/types.ts'
import { AdminDashboardPage } from '../src/features/admin/pages/AdminDashboardPage.tsx'
import { AdminProposalDetailPage } from '../src/features/admin/pages/AdminProposalDetailPage.tsx'
import { AdminWorkOrderDetailPage } from '../src/features/admin/pages/AdminWorkOrderDetailPage.tsx'
import { AdminCompletionReportDetailPage } from '../src/features/admin/pages/AdminCompletionReportDetailPage.tsx'
import { AdminDocumentDetailPage } from '../src/features/admin/pages/AdminDocumentDetailPage.tsx'
import { AdminComplaintDetailPage } from '../src/features/admin/pages/AdminComplaintDetailPage.tsx'
import {
  createTestClient,
  errorResponse,
  jsonResponse,
  requestBody,
  requestsTo,
  renderRoute,
  type RecordedRequest,
} from './helpers/customer-test-utils.tsx'

afterEach(() => {
  cleanup()
})

function page<T>(items: T[], total = items.length) {
  return { items, total, limit: items.length, offset: 0 }
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
    technician_recommendations: [
      {
        technician_id: 'technician-1',
        full_name: 'Ayesha Khan',
        eligible: true,
        matching_skills: ['dc_systems'],
        missing_skills: [],
        active_workload: 1,
        availability_status: 'available',
        reasons: ['Skill match'],
        rank: 1,
      },
    ],
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

function document(overrides: Partial<DocumentMetadata> = {}): DocumentMetadata {
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
    ingestion_status: 'ready',
    ingestion_error: null,
    ingested_at: '2026-02-01T08:00:00Z',
    is_active: false,
    created_at: '2026-02-01T08:00:00Z',
    ...overrides,
  }
}

test('admin dashboard summarizes every operational queue', async () => {
  const requests: RecordedRequest[] = []
  const client = createTestClient((request) => {
    const path = request.url.pathname
    if (path === '/api/v1/admin/complaints') {
      return jsonResponse(page([complaint()], 12))
    }
    if (path === '/api/v1/admin/work-orders') {
      return jsonResponse(page([workOrder()], 7))
    }
    if (path === '/api/v1/admin/work-order-proposals') {
      return jsonResponse(page([proposal()], 3))
    }
    if (path === '/api/v1/admin/completion-reports') {
      return jsonResponse(page([completionReport()], 2))
    }
    if (path === '/api/v1/admin/workflow-runs') {
      return jsonResponse(page([], 1))
    }
    if (path === '/api/v1/admin/documents') {
      return jsonResponse(page([document()], 4))
    }
    if (path === '/api/v1/admin/technicians') {
      return jsonResponse(page([], 5))
    }
    return errorResponse(404, 'not_found', 'Unexpected request')
  }, requests)

  renderRoute(client, <AdminDashboardPage />, {
    initialEntry: '/admin',
    path: '/admin',
  })

  assert.ok(await screen.findByText('Operations dashboard'))
  assert.ok(await screen.findByText('12'))
  assert.ok(screen.getByText('7'))
  assert.ok(screen.getAllByText('3').length > 0)
  assert.ok(screen.getByText('2'))
  assert.ok(screen.getByText('5'))
  assert.ok(screen.getByText('4'))
  assert.ok(
    screen.getByText(
      'Active count is based on 1 of 7 work orders loaded in this view.',
    ),
  )
  assert.ok(
    screen.getByText(
      'Active count is based on 1 of 4 documents loaded in this view.',
    ),
  )
  assert.ok(screen.getByText('1 active in loaded view'))
  assert.ok(screen.getByText('0 active in loaded view'))
  assert.ok(
    requestsTo(requests, '/api/v1/admin/work-order-proposals').length >= 2,
  )
})

test('administrator approves a proposal with a selected technician', async () => {
  const requests: RecordedRequest[] = []
  const client = createTestClient((request) => {
    if (
      request.url.pathname ===
        '/api/v1/admin/work-order-proposals/proposal-1' &&
      method(request) === 'GET'
    ) {
      return jsonResponse(proposal())
    }
    if (
      request.url.pathname ===
        '/api/v1/admin/work-order-proposals/proposal-1/approve' &&
      method(request) === 'POST'
    ) {
      return jsonResponse(
        proposal({
          status: 'approved',
          selected_technician_id: 'technician-1',
          resulting_work_order_id: 'work-order-1',
        }),
      )
    }
    return errorResponse(404, 'not_found', 'Unexpected request')
  }, requests)

  renderRoute(client, <AdminProposalDetailPage />, {
    initialEntry: '/admin/proposals/proposal-1',
    path: '/admin/proposals/:proposalId',
  })

  assert.ok(await screen.findByText('Review decision'))
  fireEvent.change(
    screen.getByLabelText('Assign technician after approval'),
    { target: { value: 'technician-1' } },
  )
  fireEvent.click(screen.getByRole('button', { name: 'Approve proposal' }))

  assert.ok(await screen.findByText('Proposal approved and work order created.'))
  const approveRequests = requestsTo(
    requests,
    '/api/v1/admin/work-order-proposals/proposal-1/approve',
  )
  assert.equal(approveRequests.length, 1)
  assert.deepEqual(requestBody(approveRequests[0]), {
    technician_id: 'technician-1',
  })
})

test('administrator moves a work order through the lifecycle', async () => {
  const requests: RecordedRequest[] = []
  const client = createTestClient((request) => {
    const path = request.url.pathname
    if (path === '/api/v1/admin/work-orders/work-order-1') {
      return jsonResponse(workOrder())
    }
    if (path === '/api/v1/admin/assignments') {
      return jsonResponse(page([assignment()]))
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
      return jsonResponse(workOrder({ status: 'pending_verification' }))
    }
    return errorResponse(404, 'not_found', 'Unexpected request')
  }, requests)

  renderRoute(client, <AdminWorkOrderDetailPage />, {
    initialEntry: '/admin/work-orders/work-order-1',
    path: '/admin/work-orders/:workOrderId',
  })

  assert.ok(await screen.findByText('Status actions'))
  fireEvent.click(
    screen.getByRole('button', { name: 'Move to Awaiting verification' }),
  )

  assert.ok(
    await screen.findByText('Work order moved to pending verification.'),
  )
  const statusRequests = requestsTo(
    requests,
    '/api/v1/admin/work-orders/work-order-1/status',
  )
  assert.equal(statusRequests.length, 1)
  assert.deepEqual(requestBody(statusRequests[0]), {
    status: 'pending_verification',
  })
})

test('administrator verifies submitted completion evidence', async () => {
  const requests: RecordedRequest[] = []
  const client = createTestClient((request) => {
    if (
      request.url.pathname ===
        '/api/v1/admin/completion-reports/completion-report-1' &&
      method(request) === 'GET'
    ) {
      return jsonResponse(completionReport())
    }
    if (
      request.url.pathname ===
        '/api/v1/admin/completion-reports/completion-report-1' &&
      method(request) === 'PATCH'
    ) {
      return jsonResponse(
        completionReport({
          evidence_status: 'verified',
          verified_at: '2026-02-05T08:00:00Z',
        }),
      )
    }
    return errorResponse(404, 'not_found', 'Unexpected request')
  }, requests)

  renderRoute(client, <AdminCompletionReportDetailPage />, {
    initialEntry: '/admin/completion-reports/completion-report-1',
    path: '/admin/completion-reports/:completionReportId',
  })

  assert.ok(await screen.findByText('Verification decision'))
  fireEvent.click(screen.getByRole('button', { name: 'Verify evidence' }))

  assert.ok(await screen.findByText('Evidence verified.'))
  const patchRequests = requestsTo(
    requests,
    '/api/v1/admin/completion-reports/completion-report-1',
  ).filter((request) => method(request) === 'PATCH')
  assert.equal(patchRequests.length, 1)
  assert.deepEqual(requestBody(patchRequests[0]), {
    evidence_status: 'verified',
    verification_notes: null,
  })
})

test('administrator activates a ready document', async () => {
  const requests: RecordedRequest[] = []
  const client = createTestClient((request) => {
    if (
      request.url.pathname === '/api/v1/admin/documents/document-1' &&
      method(request) === 'GET'
    ) {
      return jsonResponse(document())
    }
    if (
      request.url.pathname === '/api/v1/admin/documents/document-1/chunks'
    ) {
      return jsonResponse(page([]))
    }
    if (
      request.url.pathname ===
        '/api/v1/admin/documents/document-1/activate' &&
      method(request) === 'POST'
    ) {
      return jsonResponse(document({ is_active: true }))
    }
    return errorResponse(404, 'not_found', 'Unexpected request')
  }, requests)

  renderRoute(client, <AdminDocumentDetailPage />, {
    initialEntry: '/admin/documents/document-1',
    path: '/admin/documents/:documentId',
  })

  assert.ok(await screen.findByText('Solis S6 manual'))
  fireEvent.click(screen.getByRole('button', { name: 'Activate' }))

  assert.ok(await screen.findByText('Document activated.'))
  assert.equal(
    requestsTo(
      requests,
      '/api/v1/admin/documents/document-1/activate',
    ).length,
    1,
  )
})

test('administrator starts proposal generation for an eligible complaint', async () => {
  const requests: RecordedRequest[] = []
  const workflowAccepted: WorkflowRunAccepted = {
    workflow_run_id: 'workflow-1',
    complaint_id: 'complaint-1',
    workflow_type: 'work_order_proposal',
    status: 'running',
    current_step: 'diagnose',
  }
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
      return jsonResponse(workflowAccepted, 202)
    }
    return errorResponse(404, 'not_found', 'Unexpected request')
  }, requests)

  renderRoute(client, <AdminComplaintDetailPage />, {
    initialEntry: '/admin/complaints/complaint-1',
    path: '/admin/complaints/:complaintId',
  })

  assert.ok(await screen.findByText('Work-order preparation'))
  fireEvent.click(screen.getByRole('button', { name: 'Generate proposal' }))

  assert.ok(
    await screen.findByText(
      'Proposal generation started. The new proposal will appear when the workflow completes.',
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
