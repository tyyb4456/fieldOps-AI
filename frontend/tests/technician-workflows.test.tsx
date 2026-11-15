import './helpers/dom.ts'
import React from 'react'
import assert from 'node:assert/strict'
import test, { afterEach } from 'node:test'
import {
  act,
  cleanup,
  fireEvent,
  screen,
  within,
} from '@testing-library/react'
import type { Assignment } from '../src/features/assignments/types.ts'
import type { CompletionReport } from '../src/features/work-orders/types.ts'
import type { KnowledgeAnswer } from '../src/features/knowledge/types.ts'
import type { ServiceRecord } from '../src/features/work-orders/types.ts'
import type { WorkOrder } from '../src/features/work-orders/types.ts'
import type { WorkOrderStatus } from '../src/lib/api/types.ts'
import { TechnicianAssignmentsPage } from '../src/features/technicians/pages/TechnicianAssignmentsPage.tsx'
import { TechnicianDashboardPage } from '../src/features/technicians/pages/TechnicianDashboardPage.tsx'
import { TechnicianServiceRecordDetailPage } from '../src/features/technicians/pages/TechnicianServiceRecordDetailPage.tsx'
import { TechnicianTechnicalReferencesPage } from '../src/features/technicians/pages/TechnicianTechnicalReferencesPage.tsx'
import { TechnicianWorkOrderDetailPage } from '../src/features/technicians/pages/TechnicianWorkOrderDetailPage.tsx'
import { TechnicianWorkOrdersPage } from '../src/features/technicians/pages/TechnicianWorkOrdersPage.tsx'
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

function page<T>(
  items: T[],
  total = items.length,
  offset = 0,
): {
  items: T[]
  total: number
  limit: number
  offset: number
} {
  return { items, total, limit: items.length, offset }
}

function workOrder(overrides: Partial<WorkOrder> = {}): WorkOrder {
  return {
    id: 'work-order-1',
    complaint_id: 'complaint-1',
    equipment_id: 'equipment-1',
    title: 'Inverter shutdown',
    description: 'The inverter shuts down shortly after sunrise.',
    diagnostic_checklist: ['Verify DC input', 'Inspect error log'],
    priority: 'high',
    status: 'assigned',
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
    assignment_status: 'offered',
    assigned_at: '2026-02-02T09:00:00Z',
    accepted_at: null,
    rejected_at: null,
    ...overrides,
  }
}

function serviceRecord(overrides: Partial<ServiceRecord> = {}): ServiceRecord {
  return {
    id: 'service-record-1',
    equipment_id: 'equipment-1',
    work_order_id: 'work-order-1',
    technician_id: 'technician-1',
    findings: 'Loose DC connector.',
    work_performed: 'Reseated and secured the DC connector.',
    parts_used: ['Connector clip'],
    recorded_at: '2026-02-03T10:00:00Z',
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

function method(request: RecordedRequest): string {
  return request.init.method ?? 'GET'
}

function summaryCard(label: string): HTMLElement {
  const candidates = screen.getAllByText(label)
  const labelNode =
    candidates.find(
      (node) =>
        node instanceof HTMLElement && node.className.includes('uppercase'),
    ) ?? candidates[0]
  const card = labelNode?.parentElement
  assert.ok(card)
  return card
}

test('technician dashboard uses API totals and accepts an offer', async () => {
  const requests: RecordedRequest[] = []
  const client = createTestClient((request) => {
    if (
      request.url.pathname === '/api/v1/assignments/assignment-1/accept' &&
      method(request) === 'POST'
    ) {
      return jsonResponse(
        assignment({
          assignment_status: 'accepted',
          accepted_at: '2026-02-05T08:00:00Z',
        }),
      )
    }
    if (request.url.pathname === '/api/v1/assignments') {
      return jsonResponse(page([assignment()], 7))
    }
    if (request.url.pathname === '/api/v1/work-orders') {
      return jsonResponse(
        page([workOrder({ status: 'assigned' })], 42),
      )
    }
    return errorResponse(404, 'not_found', 'Unexpected request')
  }, requests)

  renderRoute(client, <TechnicianDashboardPage />, {
    initialEntry: '/technician',
    path: '/technician',
  })

  assert.ok(await screen.findByText('Your field work at a glance'))
  assert.ok(
    within(summaryCard('Offered assignments')).getByText('7'),
  )
  assert.ok(
    within(summaryCard('Visible work orders')).getByText('42'),
  )
  assert.ok(
    screen.getByText(
      'Total reported by the API. 1 of 7 offered assignments loaded in this view.',
    ),
  )
  assert.ok(
    screen.getByText(
      'Status counts are based on the 1 work orders loaded in this view (of 42 total).',
    ),
  )
  assert.ok((await screen.findAllByText('Inverter shutdown')).length > 0)

  fireEvent.click(screen.getByRole('button', { name: 'Accept assignment' }))

  assert.ok(
    await screen.findByText(
      'Assignment accepted. The work order is now in your work orders.',
    ),
  )
  const accept = requestsTo(
    requests,
    '/api/v1/assignments/assignment-1/accept',
  ).filter((request) => method(request) === 'POST')
  assert.equal(accept.length, 1)
})

test('technician assignments page rejects an offer after confirmation', async () => {
  const requests: RecordedRequest[] = []
  const client = createTestClient((request) => {
    if (
      request.url.pathname === '/api/v1/assignments/assignment-1/reject' &&
      method(request) === 'POST'
    ) {
      return jsonResponse(
        assignment({
          assignment_status: 'rejected',
          rejected_at: '2026-02-05T08:00:00Z',
        }),
      )
    }
    if (request.url.pathname === '/api/v1/assignments') {
      return jsonResponse(page([assignment()]))
    }
    if (request.url.pathname === '/api/v1/work-orders') {
      return jsonResponse(page([workOrder()]))
    }
    return errorResponse(404, 'not_found', 'Unexpected request')
  }, requests)
  window.confirm = () => true

  renderRoute(client, <TechnicianAssignmentsPage />, {
    initialEntry: '/technician/assignments',
    path: '/technician/assignments',
  })

  assert.ok(await screen.findByText('Offered assignments'))
  assert.ok(screen.getByText('1 offered assignment'))
  fireEvent.click(screen.getByRole('button', { name: 'Reject assignment' }))

  assert.ok(
    await screen.findByText(
      'Assignment rejected. The service team can reassign it.',
    ),
  )
  assert.equal(
    requestsTo(requests, '/api/v1/assignments/assignment-1/reject').filter(
      (request) => method(request) === 'POST',
    ).length,
    1,
  )
})

test('technician work orders apply supported status filters', async () => {
  const requests: RecordedRequest[] = []
  const client = createTestClient((request) => {
    if (request.url.pathname !== '/api/v1/work-orders') {
      return errorResponse(404, 'not_found', 'Unexpected request')
    }
    if (request.url.searchParams.get('status') === 'in_progress') {
      return jsonResponse(
        page([
          workOrder({
            id: 'work-order-2',
            title: 'Battery balancing',
            status: 'in_progress',
          }),
        ]),
      )
    }
    return jsonResponse(page([workOrder()]))
  }, requests)

  renderRoute(client, <TechnicianWorkOrdersPage />, {
    initialEntry: '/technician/work-orders',
    path: '/technician/work-orders',
  })

  assert.ok(await screen.findByText('Inverter shutdown'))
  fireEvent.change(screen.getByLabelText('Status'), {
    target: { value: 'in_progress' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Apply filters' }))

  assert.ok(await screen.findByText('Battery balancing'))
  assert.ok(
    requests.some(
      (request) =>
        request.url.pathname === '/api/v1/work-orders' &&
        request.url.searchParams.get('status') === 'in_progress',
    ),
  )
})

test('work-order detail records service activity and submits evidence', async () => {
  const requests: RecordedRequest[] = []
  let status: WorkOrderStatus = 'accepted'
  let records: ServiceRecord[] = [serviceRecord()]
  let reports: CompletionReport[] = []

  const client = createTestClient((request) => {
    if (request.url.pathname === '/api/v1/work-orders/work-order-1') {
      return jsonResponse(workOrder({ status }))
    }
    if (request.url.pathname === '/api/v1/assignments') {
      return jsonResponse(
        page([
          assignment({
            assignment_status: 'accepted',
            accepted_at: '2026-02-02T10:00:00Z',
          }),
        ]),
      )
    }
    if (
      request.url.pathname ===
      '/api/v1/work-orders/work-order-1/service-records'
    ) {
      if (method(request) === 'POST') {
        const body = requestBody(request) as {
          findings: string | null
          work_performed: string | null
          parts_used: string[]
        }
        const created = serviceRecord({
          id: `service-record-${records.length + 1}`,
          ...body,
        })
        records = [...records, created]
        return jsonResponse(created, 201)
      }
      return jsonResponse(page(records))
    }
    if (
      request.url.pathname ===
      '/api/v1/work-orders/work-order-1/completion-reports'
    ) {
      if (method(request) === 'POST') {
        const body = requestBody(request) as {
          service_record_id: string
          summary: string
        }
        const created = completionReport(body)
        reports = [created]
        return jsonResponse(created, 201)
      }
      return jsonResponse(page(reports))
    }
    if (
      request.url.pathname === '/api/v1/work-orders/work-order-1/status' &&
      method(request) === 'POST'
    ) {
      const body = requestBody(request) as { status: WorkOrderStatus }
      status = body.status
      return jsonResponse(workOrder({ status }))
    }
    return errorResponse(404, 'not_found', 'Unexpected request')
  }, requests)
  window.confirm = () => true

  renderRoute(client, <TechnicianWorkOrderDetailPage />, {
    initialEntry: '/technician/work-orders/work-order-1',
    path: '/technician/work-orders/:workOrderId',
  })

  assert.ok(await screen.findByText('Inverter shutdown'))
  assert.ok(screen.getByText('Work actions'))
  assert.ok(screen.getByText('Reseated and secured the DC connector.'))

  fireEvent.click(screen.getByRole('button', { name: 'Add service record' }))
  fireEvent.change(screen.getByLabelText('Findings'), {
    target: { value: 'Corroded fuse holder.' },
  })
  fireEvent.change(screen.getByLabelText('Work performed'), {
    target: { value: 'Replaced the fuse and cleaned the holder.' },
  })
  fireEvent.change(screen.getByLabelText('Parts used'), {
    target: { value: 'Fuse\nCleaning kit' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Save service record' }))

  assert.ok(
    await screen.findByText('Service record added to this work order.'),
  )
  const createRecord = requestsTo(
    requests,
    '/api/v1/work-orders/work-order-1/service-records',
  ).find((request) => method(request) === 'POST')
  assert.ok(createRecord)
  assert.deepEqual(requestBody(createRecord), {
    findings: 'Corroded fuse holder.',
    work_performed: 'Replaced the fuse and cleaned the holder.',
    parts_used: ['Fuse', 'Cleaning kit'],
  })
  assert.ok(
    await screen.findByText('Replaced the fuse and cleaned the holder.'),
  )

  fireEvent.change(screen.getByLabelText(/Completion summary/), {
    target: { value: 'Replaced the fuse and verified output.' },
  })
  fireEvent.click(
    screen.getByRole('button', { name: 'Submit completion report' }),
  )

  assert.ok(
    await screen.findByText('Completion report submitted for verification.'),
  )
  const createReport = requestsTo(
    requests,
    '/api/v1/work-orders/work-order-1/completion-reports',
  ).find((request) => method(request) === 'POST')
  assert.ok(createReport)
  assert.deepEqual(requestBody(createReport), {
    service_record_id: 'service-record-1',
    summary: 'Replaced the fuse and verified output.',
  })

  fireEvent.click(await screen.findByRole('button', { name: 'Start work' }))
  assert.ok(
    await screen.findByText('Work order moved to in progress.'),
  )

  fireEvent.click(
    await screen.findByRole('button', { name: 'Submit for verification' }),
  )
  assert.ok(
    await screen.findByText('Work order moved to pending verification.'),
  )

  const statusUpdates = requestsTo(
    requests,
    '/api/v1/work-orders/work-order-1/status',
  )
    .filter((request) => method(request) === 'POST')
    .map((request) => requestBody(request))
  assert.deepEqual(statusUpdates, [
    { status: 'in_progress' },
    { status: 'pending_verification' },
  ])
})

test('pending completion report summaries can be edited', async () => {
  const requests: RecordedRequest[] = []
  let report = completionReport()

  const client = createTestClient((request) => {
    if (request.url.pathname === '/api/v1/work-orders/work-order-1') {
      return jsonResponse(workOrder({ status: 'accepted' }))
    }
    if (request.url.pathname === '/api/v1/assignments') {
      return jsonResponse(
        page([
          assignment({
            assignment_status: 'accepted',
            accepted_at: '2026-02-02T10:00:00Z',
          }),
        ]),
      )
    }
    if (
      request.url.pathname ===
      '/api/v1/work-orders/work-order-1/service-records'
    ) {
      return jsonResponse(page([serviceRecord()]))
    }
    if (
      request.url.pathname ===
      '/api/v1/work-orders/work-order-1/completion-reports'
    ) {
      return jsonResponse(page([report]))
    }
    if (
      request.url.pathname === '/api/v1/completion-reports/completion-report-1' &&
      method(request) === 'PATCH'
    ) {
      const body = requestBody(request) as { summary: string }
      report = { ...report, summary: body.summary }
      return jsonResponse(report)
    }
    return errorResponse(404, 'not_found', 'Unexpected request')
  }, requests)

  renderRoute(client, <TechnicianWorkOrderDetailPage />, {
    initialEntry: '/technician/work-orders/work-order-1',
    path: '/technician/work-orders/:workOrderId',
  })

  assert.ok(await screen.findByText('Reseated the DC connector and verified output.'))
  fireEvent.click(screen.getByRole('button', { name: 'Edit summary' }))
  fireEvent.change(screen.getByLabelText(/Completion summary/), {
    target: { value: 'Updated completion summary.' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Save summary' }))

  assert.ok(
    await screen.findByText('Completion report summary updated.'),
  )
  const patch = requestsTo(
    requests,
    '/api/v1/completion-reports/completion-report-1',
  ).find((request) => method(request) === 'PATCH')
  assert.ok(patch)
  assert.deepEqual(requestBody(patch), { summary: 'Updated completion summary.' })
})

test('service record detail updates findings, work, and parts', async () => {
  const requests: RecordedRequest[] = []
  let record = serviceRecord()

  const client = createTestClient((request) => {
    if (request.url.pathname === '/api/v1/service-records/service-record-1') {
      if (method(request) === 'PATCH') {
        const body = requestBody(request) as Partial<ServiceRecord>
        record = { ...record, ...body }
        return jsonResponse(record)
      }
      return jsonResponse(record)
    }
    if (request.url.pathname === '/api/v1/work-orders/work-order-1') {
      return jsonResponse(workOrder({ status: 'in_progress' }))
    }
    return errorResponse(404, 'not_found', 'Unexpected request')
  }, requests)

  renderRoute(client, <TechnicianServiceRecordDetailPage />, {
    initialEntry: '/technician/service-records/service-record-1',
    path: '/technician/service-records/:serviceRecordId',
  })

  assert.ok(await screen.findByText('Loose DC connector.'))
  fireEvent.click(screen.getByRole('button', { name: 'Edit service record' }))
  fireEvent.change(screen.getByLabelText('Findings'), {
    target: { value: 'Loose DC connector and worn seal.' },
  })
  fireEvent.change(screen.getByLabelText('Work performed'), {
    target: { value: 'Reseated the connector and replaced the seal.' },
  })
  fireEvent.change(screen.getByLabelText('Parts used'), {
    target: { value: 'Seal kit\nConnector clip' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

  assert.ok(await screen.findByText('Service record updated.'))
  const patch = requestsTo(
    requests,
    '/api/v1/service-records/service-record-1',
  ).find((request) => method(request) === 'PATCH')
  assert.ok(patch)
  assert.deepEqual(requestBody(patch), {
    findings: 'Loose DC connector and worn seal.',
    work_performed: 'Reseated the connector and replaced the seal.',
    parts_used: ['Seal kit', 'Connector clip'],
  })
  assert.ok(
    screen.getByText('Reseated the connector and replaced the seal.'),
  )
})

test('technical references search documents and request cited answers', async () => {
  const requests: RecordedRequest[] = []
  const answer: KnowledgeAnswer = {
    answer: 'Check the DC isolator and confirm input voltage.',
    status: 'answered',
    citations: [
      {
        source_id: 'source-1',
        chunk_id: 'chunk-1',
        document_id: 'document-1',
        document_name: 'Inverter service manual',
        manufacturer: 'Acme',
        model: 'Sun 500',
        version: '2.1',
        page_number: 12,
        chunk_index: 3,
        excerpt: 'Verify the DC isolator state before opening the cabinet.',
      },
    ],
    evidence_summary: 'One relevant passage was found.',
    insufficient_evidence: false,
    missing_information: [],
    warnings: [],
  }

  const client = createTestClient((request) => {
    if (
      request.url.pathname === '/api/v1/knowledge/search' &&
      method(request) === 'POST'
    ) {
      return jsonResponse({
        items: [
          {
            chunk_id: 'chunk-1',
            document_id: 'document-1',
            document_name: 'Inverter service manual',
            manufacturer: 'Acme',
            model: 'Sun 500',
            version: '2.1',
            page_number: 12,
            chunk_index: 3,
            content: 'Verify the DC isolator state before opening the cabinet.',
            distance: 0.12,
            similarity: 0.88,
          },
        ],
        top_k: 5,
      })
    }
    if (
      request.url.pathname === '/api/v1/knowledge/answer' &&
      method(request) === 'POST'
    ) {
      return jsonResponse(answer)
    }
    return errorResponse(404, 'not_found', 'Unexpected request')
  }, requests)

  renderRoute(client, <TechnicianTechnicalReferencesPage />, {
    initialEntry: '/technician/technical-references',
    path: '/technician/technical-references',
  })

  assert.ok(await screen.findByText('Search technical documentation'))
  fireEvent.change(screen.getByLabelText(/Search technical documents/), {
    target: { value: '  inverter DC isolator  ' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Search documents' }))

  assert.ok(await screen.findByText('Inverter service manual'))
  assert.ok(
    screen.getByText('Verify the DC isolator state before opening the cabinet.'),
  )
  const search = requestsTo(requests, '/api/v1/knowledge/search')[0]
  assert.ok(search)
  assert.deepEqual(requestBody(search), {
    query: 'inverter DC isolator',
    manufacturer: null,
    model: null,
    top_k: 5,
  })

  fireEvent.change(screen.getByLabelText(/Ask a technical question/), {
    target: { value: 'How do I check the DC isolator?' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Get grounded answer' }))

  assert.ok(
    await screen.findByText(
      'Check the DC isolator and confirm input voltage.',
    ),
  )
  assert.ok(screen.getByText('One relevant passage was found.'))
  assert.ok(screen.getByText('Source source-1'))
})

test('accepting an offer from work-order detail unlocks work actions', async () => {
  const requests: RecordedRequest[] = []
  let assignmentStatus: Assignment['assignment_status'] = 'offered'
  let workOrderStatus: WorkOrderStatus = 'assigned'

  const client = createTestClient((request) => {
    if (request.url.pathname === '/api/v1/work-orders/work-order-1') {
      return jsonResponse(workOrder({ status: workOrderStatus }))
    }
    if (request.url.pathname === '/api/v1/assignments') {
      return jsonResponse(
        page([
          assignment({
            assignment_status: assignmentStatus,
            accepted_at:
              assignmentStatus === 'accepted'
                ? '2026-02-05T08:00:00Z'
                : null,
          }),
        ]),
      )
    }
    if (
      request.url.pathname === '/api/v1/assignments/assignment-1/accept' &&
      method(request) === 'POST'
    ) {
      assignmentStatus = 'accepted'
      workOrderStatus = 'accepted'
      return jsonResponse(
        assignment({
          assignment_status: 'accepted',
          accepted_at: '2026-02-05T08:00:00Z',
        }),
      )
    }
    if (
      request.url.pathname ===
      '/api/v1/work-orders/work-order-1/service-records'
    ) {
      return jsonResponse(page([]))
    }
    if (
      request.url.pathname ===
      '/api/v1/work-orders/work-order-1/completion-reports'
    ) {
      return jsonResponse(page([]))
    }
    return errorResponse(404, 'not_found', 'Unexpected request')
  }, requests)

  renderRoute(client, <TechnicianWorkOrderDetailPage />, {
    initialEntry: '/technician/work-orders/work-order-1',
    path: '/technician/work-orders/:workOrderId',
  })

  assert.ok(await screen.findByText('Assignment offer'))
  fireEvent.click(screen.getByRole('button', { name: 'Accept assignment' }))

  assert.ok(
    await screen.findByText('Assignment accepted. You can start work now.'),
  )
  assert.ok(await screen.findByRole('button', { name: 'Start work' }))
  assert.equal(
    screen.queryByRole('button', { name: 'Accept assignment' }),
    null,
  )
})

test('rejecting an offer from detail redirects with a notice', async () => {
  const requests: RecordedRequest[] = []
  const client = createTestClient((request) => {
    if (request.url.pathname === '/api/v1/work-orders/work-order-1') {
      return jsonResponse(workOrder({ status: 'assigned' }))
    }
    if (request.url.pathname === '/api/v1/assignments') {
      return jsonResponse(page([assignment()]))
    }
    if (
      request.url.pathname === '/api/v1/assignments/assignment-1/reject' &&
      method(request) === 'POST'
    ) {
      return jsonResponse(
        assignment({
          assignment_status: 'rejected',
          rejected_at: '2026-02-05T08:00:00Z',
        }),
      )
    }
    if (
      request.url.pathname ===
      '/api/v1/work-orders/work-order-1/service-records'
    ) {
      return jsonResponse(page([]))
    }
    if (
      request.url.pathname ===
      '/api/v1/work-orders/work-order-1/completion-reports'
    ) {
      return jsonResponse(page([]))
    }
    return errorResponse(404, 'not_found', 'Unexpected request')
  }, requests)
  window.confirm = () => true

  renderRoute(client, <TechnicianWorkOrderDetailPage />, {
    initialEntry: '/technician/work-orders/work-order-1',
    path: '/technician/work-orders/:workOrderId',
  })

  assert.ok(await screen.findByText('Assignment offer'))
  fireEvent.click(screen.getByRole('button', { name: 'Reject assignment' }))

  const location = await screen.findByTestId('location')
  assert.equal(location.textContent, '/technician/assignments')
  assert.equal(
    location.getAttribute('data-notice'),
    'Assignment rejected. The service team can reassign it.',
  )
  assert.equal(
    requestsTo(requests, '/api/v1/assignments/assignment-1/reject').filter(
      (request) => method(request) === 'POST',
    ).length,
    1,
  )
})

test('stale assignment actions show a safe conflict without success', async () => {
  const requests: RecordedRequest[] = []
  const client = createTestClient((request) => {
    if (request.url.pathname === '/api/v1/assignments') {
      return jsonResponse(page([assignment()]))
    }
    if (request.url.pathname === '/api/v1/work-orders') {
      return jsonResponse(page([workOrder()]))
    }
    if (
      request.url.pathname === '/api/v1/assignments/assignment-1/accept' &&
      method(request) === 'POST'
    ) {
      return errorResponse(
        409,
        'invalid_assignment_state',
        'Only an offered assignment can be accepted',
      )
    }
    return errorResponse(404, 'not_found', 'Unexpected request')
  }, requests)

  renderRoute(client, <TechnicianAssignmentsPage />, {
    initialEntry: '/technician/assignments',
    path: '/technician/assignments',
  })

  assert.ok(await screen.findByText('Offered assignments'))
  fireEvent.click(screen.getByRole('button', { name: 'Accept assignment' }))

  assert.ok(
    await screen.findByText(
      'This assignment can no longer be changed. It may have been accepted, rejected, or withdrawn.',
    ),
  )
  assert.equal(
    screen.queryByText(
      'Assignment accepted. The work order is now in your work orders.',
    ),
    null,
  )
})

test('assignment actions prevent duplicate submissions', async () => {
  const requests: RecordedRequest[] = []
  let resolveAccept: ((response: Response) => void) | undefined

  const client = createTestClient((request) => {
    if (request.url.pathname === '/api/v1/assignments') {
      return jsonResponse(page([assignment()]))
    }
    if (request.url.pathname === '/api/v1/work-orders') {
      return jsonResponse(page([workOrder()]))
    }
    if (
      request.url.pathname === '/api/v1/assignments/assignment-1/accept' &&
      method(request) === 'POST'
    ) {
      return new Promise<Response>((resolve) => {
        resolveAccept = resolve
      })
    }
    return errorResponse(404, 'not_found', 'Unexpected request')
  }, requests)

  renderRoute(client, <TechnicianAssignmentsPage />, {
    initialEntry: '/technician/assignments',
    path: '/technician/assignments',
  })

  assert.ok(await screen.findByText('Offered assignments'))
  fireEvent.click(screen.getByRole('button', { name: 'Accept assignment' }))
  assert.ok(await screen.findByRole('button', { name: 'Accepting...' }))

  fireEvent.click(screen.getByRole('button', { name: 'Accepting...' }))
  assert.equal(
    requestsTo(requests, '/api/v1/assignments/assignment-1/accept').filter(
      (request) => method(request) === 'POST',
    ).length,
    1,
  )

  const resolve = resolveAccept
  assert.ok(resolve)
  await act(async () => {
    resolve(
      jsonResponse(
        assignment({
          assignment_status: 'accepted',
          accepted_at: '2026-02-05T08:00:00Z',
        }),
      ),
    )
  })

  assert.ok(
    await screen.findByText(
      'Assignment accepted. The work order is now in your work orders.',
    ),
  )
  assert.equal(
    requestsTo(requests, '/api/v1/assignments/assignment-1/accept').filter(
      (request) => method(request) === 'POST',
    ).length,
    1,
  )
})

test('invalid work-order transitions show a safe message', async () => {
  const requests: RecordedRequest[] = []
  const client = createTestClient((request) => {
    if (request.url.pathname === '/api/v1/work-orders/work-order-1') {
      return jsonResponse(workOrder({ status: 'accepted' }))
    }
    if (request.url.pathname === '/api/v1/assignments') {
      return jsonResponse(
        page([
          assignment({
            assignment_status: 'accepted',
            accepted_at: '2026-02-02T10:00:00Z',
          }),
        ]),
      )
    }
    if (
      request.url.pathname ===
      '/api/v1/work-orders/work-order-1/service-records'
    ) {
      return jsonResponse(page([serviceRecord()]))
    }
    if (
      request.url.pathname ===
      '/api/v1/work-orders/work-order-1/completion-reports'
    ) {
      return jsonResponse(page([]))
    }
    if (
      request.url.pathname === '/api/v1/work-orders/work-order-1/status' &&
      method(request) === 'POST'
    ) {
      return errorResponse(
        409,
        'invalid_status_transition',
        'Work order cannot be changed in its current state.',
      )
    }
    return errorResponse(404, 'not_found', 'Unexpected request')
  }, requests)

  renderRoute(client, <TechnicianWorkOrderDetailPage />, {
    initialEntry: '/technician/work-orders/work-order-1',
    path: '/technician/work-orders/:workOrderId',
  })

  assert.ok(await screen.findByRole('button', { name: 'Start work' }))
  fireEvent.click(screen.getByRole('button', { name: 'Start work' }))

  assert.ok(
    await screen.findByText(
      'The work order cannot be moved to that state right now.',
    ),
  )
  assert.equal(
    screen.queryByText('Work order moved to in progress.'),
    null,
  )
})

test('service record detail is read-only after active service', async () => {
  const client = createTestClient((request) => {
    if (request.url.pathname === '/api/v1/service-records/service-record-1') {
      return jsonResponse(serviceRecord())
    }
    if (request.url.pathname === '/api/v1/work-orders/work-order-1') {
      return jsonResponse(workOrder({ status: 'pending_verification' }))
    }
    return errorResponse(404, 'not_found', 'Unexpected request')
  })

  renderRoute(client, <TechnicianServiceRecordDetailPage />, {
    initialEntry: '/technician/service-records/service-record-1',
    path: '/technician/service-records/:serviceRecordId',
  })

  assert.ok(await screen.findByText('Loose DC connector.'))
  assert.equal(
    screen.queryByRole('button', { name: 'Edit service record' }),
    null,
  )
  assert.ok(
    screen.getByText(
      'This service record is read-only because the work order is no longer in an editable state.',
    ),
  )
})

test('stale service-record edits show a safe conflict', async () => {
  const client = createTestClient((request) => {
    if (request.url.pathname === '/api/v1/service-records/service-record-1') {
      if (method(request) === 'PATCH') {
        return errorResponse(
          409,
          'invalid_service_record_state',
          'Submitted service records are immutable once the work order leaves active service',
        )
      }
      return jsonResponse(serviceRecord())
    }
    if (request.url.pathname === '/api/v1/work-orders/work-order-1') {
      return jsonResponse(workOrder({ status: 'in_progress' }))
    }
    return errorResponse(404, 'not_found', 'Unexpected request')
  })

  renderRoute(client, <TechnicianServiceRecordDetailPage />, {
    initialEntry: '/technician/service-records/service-record-1',
    path: '/technician/service-records/:serviceRecordId',
  })

  assert.ok(await screen.findByText('Loose DC connector.'))
  fireEvent.click(screen.getByRole('button', { name: 'Edit service record' }))
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

  assert.ok(
    await screen.findByText('This service record can no longer be changed.'),
  )
  assert.equal(screen.queryByText('Service record updated.'), null)
})

test('inaccessible service record detail shows a safe not-found message', async () => {
  const client = createTestClient(() =>
    errorResponse(404, 'not_found', 'Service record not found'),
  )

  renderRoute(client, <TechnicianServiceRecordDetailPage />, {
    initialEntry: '/technician/service-records/missing-service-record',
    path: '/technician/service-records/:serviceRecordId',
  })

  assert.ok(
    await screen.findByText(
      'This service record could not be found or is not available to your account.',
    ),
  )
  assert.equal(screen.queryByText('Service record not found'), null)
})

test('verified and rejected completion reports are read-only', async () => {
  const reports = [
    completionReport({
      id: 'completion-report-1',
      summary: 'Rejected completion summary.',
      evidence_status: 'rejected',
    }),
    completionReport({
      id: 'completion-report-2',
      summary: 'Verified completion summary.',
      evidence_status: 'verified',
      verified_at: '2026-02-06T09:00:00Z',
    }),
  ]
  const client = createTestClient((request) => {
    if (request.url.pathname === '/api/v1/work-orders/work-order-1') {
      return jsonResponse(workOrder({ status: 'pending_verification' }))
    }
    if (request.url.pathname === '/api/v1/assignments') {
      return jsonResponse(
        page([
          assignment({
            assignment_status: 'accepted',
            accepted_at: '2026-02-02T10:00:00Z',
          }),
        ]),
      )
    }
    if (
      request.url.pathname ===
      '/api/v1/work-orders/work-order-1/service-records'
    ) {
      return jsonResponse(page([serviceRecord()]))
    }
    if (
      request.url.pathname ===
      '/api/v1/work-orders/work-order-1/completion-reports'
    ) {
      return jsonResponse(page(reports))
    }
    return errorResponse(404, 'not_found', 'Unexpected request')
  })

  renderRoute(client, <TechnicianWorkOrderDetailPage />, {
    initialEntry: '/technician/work-orders/work-order-1',
    path: '/technician/work-orders/:workOrderId',
  })

  assert.ok(await screen.findByText('Rejected completion summary.'))
  assert.equal(
    screen.queryByRole('button', { name: 'Edit summary' }),
    null,
  )
  assert.equal(
    screen.getAllByText(
      'Verified or rejected reports are read-only for technicians.',
    ).length,
    2,
  )
})

test('pending completion reports lock when the work order is closed', async () => {
  const client = createTestClient((request) => {
    if (request.url.pathname === '/api/v1/work-orders/work-order-1') {
      return jsonResponse(workOrder({ status: 'completed' }))
    }
    if (request.url.pathname === '/api/v1/assignments') {
      return jsonResponse(
        page([
          assignment({
            assignment_status: 'accepted',
            accepted_at: '2026-02-02T10:00:00Z',
          }),
        ]),
      )
    }
    if (
      request.url.pathname ===
      '/api/v1/work-orders/work-order-1/service-records'
    ) {
      return jsonResponse(page([serviceRecord()]))
    }
    if (
      request.url.pathname ===
      '/api/v1/work-orders/work-order-1/completion-reports'
    ) {
      return jsonResponse(page([completionReport()]))
    }
    return errorResponse(404, 'not_found', 'Unexpected request')
  })

  renderRoute(client, <TechnicianWorkOrderDetailPage />, {
    initialEntry: '/technician/work-orders/work-order-1',
    path: '/technician/work-orders/:workOrderId',
  })

  assert.ok(
    await screen.findByText('Reseated the DC connector and verified output.'),
  )
  assert.equal(
    screen.queryByRole('button', { name: 'Edit summary' }),
    null,
  )
  assert.ok(
    screen.getByText(
      'This report is read-only because the work order is no longer in an editable state.',
    ),
  )
})

test('invalid knowledge citations fail safely without mutating work orders', async () => {
  const requests: RecordedRequest[] = []
  const client = createTestClient((request) => {
    if (
      request.url.pathname === '/api/v1/knowledge/answer' &&
      method(request) === 'POST'
    ) {
      return jsonResponse({
        answer: 'Grounded answer text.',
        status: 'answered',
        citations: [
          {
            chunk_id: 'chunk-1',
            document_id: 'document-1',
            document_name: 'Inverter service manual',
            manufacturer: 'Acme',
            model: 'Sun 500',
            version: null,
            page_number: null,
            chunk_index: 0,
            excerpt: 'Verify the DC isolator state.',
          },
        ],
        evidence_summary: null,
        insufficient_evidence: false,
        missing_information: [],
        warnings: [],
      })
    }
    return errorResponse(404, 'not_found', 'Unexpected request')
  }, requests)

  renderRoute(client, <TechnicianTechnicalReferencesPage />, {
    initialEntry: '/technician/technical-references',
    path: '/technician/technical-references',
  })

  assert.ok(await screen.findByText('Search technical documentation'))
  fireEvent.change(screen.getByLabelText(/Ask a technical question/), {
    target: { value: 'How do I check the DC isolator?' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Get grounded answer' }))

  assert.ok(
    await screen.findByText(
      'The API returned a response this page could not read. Please try again.',
    ),
  )
  assert.equal(
    requests.every((request) =>
      request.url.pathname.startsWith('/api/v1/knowledge/'),
    ),
    true,
  )
})

test('inaccessible work-order detail shows a safe not-found message', async () => {
  const client = createTestClient(() =>
    errorResponse(404, 'not_found', 'Work order not found'),
  )

  renderRoute(client, <TechnicianWorkOrderDetailPage />, {
    initialEntry: '/technician/work-orders/missing-work-order',
    path: '/technician/work-orders/:workOrderId',
  })

  assert.ok(
    await screen.findByText(
      'This work order could not be found or is not available to your account.',
    ),
  )
  assert.equal(screen.queryByText('Work order not found'), null)
})
