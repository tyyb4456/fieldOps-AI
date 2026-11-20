import './helpers/dom.ts'
import React from 'react'
import assert from 'node:assert/strict'
import test, { afterEach } from 'node:test'
import { cleanup, screen } from '@testing-library/react'
import type { WorkOrderProposal } from '../src/features/work-orders/types.ts'
import {
  parseWorkOrderProposal,
} from '../src/features/admin/api.ts'
import {
  proposalStatusLabel,
  proposalStatusTone,
} from '../src/features/admin/labels.ts'
import { AdminProposalDetailPage } from '../src/features/admin/pages/AdminProposalDetailPage.tsx'
import { AdminProposalsPage } from '../src/features/admin/pages/AdminProposalsPage.tsx'
import {
  createTestClient,
  errorResponse,
  jsonResponse,
  renderRoute,
  requestsTo,
  type RecordedRequest,
} from './helpers/customer-test-utils.tsx'

afterEach(() => {
  cleanup()
})

function page<T>(items: T[], total = items.length) {
  return { items, total, limit: items.length, offset: 0 }
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

test('parser accepts a superseded proposal status', () => {
  const parsed = parseWorkOrderProposal(
    proposal({ status: 'superseded' }),
  )

  assert.equal(parsed.status, 'superseded')
})

test('admin proposal list renders pending and superseded proposals together', async () => {
  const requests: RecordedRequest[] = []
  const client = createTestClient((request) => {
    if (request.url.pathname === '/api/v1/admin/work-order-proposals') {
      return jsonResponse(
        page([
          proposal(),
          proposal({
            id: 'proposal-2',
            title: 'Superseded inverter proposal',
            status: 'superseded',
          }),
        ]),
      )
    }
    return errorResponse(404, 'not_found', 'Unexpected request')
  }, requests)

  renderRoute(client, <AdminProposalsPage />, {
    initialEntry: '/admin/proposals',
    path: '/admin/proposals',
  })

  assert.ok(await screen.findByText('Inverter shutdown proposal'))
  assert.ok(screen.getByText('Superseded inverter proposal'))
  assert.ok(screen.getAllByText('Pending approval').length >= 2)
  assert.ok(screen.getAllByText('Superseded').length >= 2)
})

test('superseded proposals use a historical label and neutral tone', () => {
  assert.equal(proposalStatusLabel('superseded'), 'Superseded')
  assert.equal(proposalStatusTone('superseded'), 'neutral')
})

test('superseded proposal detail exposes no approval or rejection actions', async () => {
  const requests: RecordedRequest[] = []
  const client = createTestClient((request) => {
    if (
      request.url.pathname ===
        '/api/v1/admin/work-order-proposals/proposal-2' &&
      (request.init.method ?? 'GET') === 'GET'
    ) {
      return jsonResponse(
        proposal({
          id: 'proposal-2',
          status: 'superseded',
        }),
      )
    }
    return errorResponse(404, 'not_found', 'Unexpected request')
  }, requests)

  renderRoute(client, <AdminProposalDetailPage />, {
    initialEntry: '/admin/proposals/proposal-2',
    path: '/admin/proposals/:proposalId',
  })

  assert.ok(await screen.findByText('Superseded proposal'))
  assert.equal(screen.queryByText('Review decision'), null)
  assert.equal(
    screen.queryByRole('button', { name: 'Approve proposal' }),
    null,
  )
  assert.equal(
    screen.queryByRole('button', { name: 'Reject proposal' }),
    null,
  )
  assert.equal(
    requestsTo(
      requests,
      '/api/v1/admin/work-order-proposals/proposal-2/approve',
    ).length,
    0,
  )
  assert.equal(
    requestsTo(
      requests,
      '/api/v1/admin/work-order-proposals/proposal-2/reject',
    ).length,
    0,
  )
})
