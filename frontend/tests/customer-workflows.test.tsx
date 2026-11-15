import './helpers/dom.ts'
import React from 'react'
import assert from 'node:assert/strict'
import test, { afterEach } from 'node:test'
import {
  cleanup,
  fireEvent,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { CustomerDashboardPage } from '../src/features/customers/pages/CustomerDashboardPage.tsx'
import { CustomerProfilePage } from '../src/features/customers/pages/CustomerProfilePage.tsx'
import { ComplaintDetailPage } from '../src/features/complaints/pages/ComplaintDetailPage.tsx'
import { ComplaintListPage } from '../src/features/complaints/pages/ComplaintListPage.tsx'
import { ComplaintNewPage } from '../src/features/complaints/pages/ComplaintNewPage.tsx'
import type { Complaint } from '../src/features/complaints/types.ts'
import { EquipmentDetailPage } from '../src/features/equipment/pages/EquipmentDetailPage.tsx'
import { EquipmentEditPage } from '../src/features/equipment/pages/EquipmentEditPage.tsx'
import { EquipmentListPage } from '../src/features/equipment/pages/EquipmentListPage.tsx'
import { EquipmentNewPage } from '../src/features/equipment/pages/EquipmentNewPage.tsx'
import type { Equipment } from '../src/features/equipment/types.ts'
import type { CustomerProfile } from '../src/features/customers/types.ts'
import {
  createTestClient,
  emptyResponse,
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

function profile(overrides: Partial<CustomerProfile> = {}): CustomerProfile {
  return {
    id: 'customer-1',
    full_name: 'Ayesha Khan',
    email: 'ayesha@example.com',
    phone: null,
    address: '12 Solar Avenue',
    preferred_language: 'en',
    is_active: true,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

function equipment(overrides: Partial<Equipment> = {}): Equipment {
  return {
    id: 'equipment-1',
    customer_id: 'customer-1',
    manufacturer: 'Acme',
    model: 'Sun 500',
    serial_number: 'SN-1',
    equipment_type: 'solar_inverter',
    installation_date: '2024-05-01',
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

function complaint(overrides: Partial<Complaint> = {}): Complaint {
  return {
    id: 'complaint-1',
    customer_id: 'customer-1',
    equipment_id: null,
    description: 'The inverter stopped producing power after sunrise.',
    reported_symptoms: [],
    reported_error_code: 'E-05',
    channel: 'web',
    status: 'received',
    priority: 'normal',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

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

function summaryCard(label: string): HTMLElement {
  const candidates = screen.getAllByText(label)
  const labelNode =
    candidates.find(
      (node) =>
        node instanceof HTMLElement &&
        node.className.includes('uppercase'),
    ) ?? candidates[0]
  const card = labelNode?.parentElement
  assert.ok(card)
  return card
}

function formFor(buttonName: string): HTMLFormElement {
  const form = screen.getByRole('button', { name: buttonName }).closest('form')
  assert.ok(form)
  return form
}

function method(request: RecordedRequest): string {
  return request.init.method ?? 'GET'
}

test('profile page loads, updates editable fields, and shows API errors', async () => {
  const requests: RecordedRequest[] = []
  let updated = false

  const client = createTestClient((request) => {
    if (request.url.pathname !== '/api/v1/customers/me') {
      return errorResponse(404, 'not_found', 'Unexpected request')
    }

    if (method(request) === 'PATCH') {
      updated = true
      const body = requestBody(request) as {
        address: string | null
        preferred_language: string | null
      }
      return jsonResponse(
        profile({
          address: body.address,
          preferred_language: body.preferred_language,
        }),
      )
    }

    return jsonResponse(profile())
  }, requests)

  renderRoute(client, <CustomerProfilePage />, {
    initialEntry: '/customer/profile',
    path: '/customer/profile',
  })

  assert.ok(await screen.findByText('Ayesha Khan'))
  const address = screen.getByLabelText('Service address')
  assert.equal((address as HTMLTextAreaElement).value, '12 Solar Avenue')

  fireEvent.change(address, { target: { value: '  99 New Street  ' } })
  fireEvent.change(screen.getByLabelText('Preferred language'), {
    target: { value: 'ur' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Save profile' }))

  assert.ok(await screen.findByText('Your profile has been updated.'))
  assert.equal(updated, true)
  const patch = requestsTo(requests, '/api/v1/customers/me').find(
    (request) => method(request) === 'PATCH',
  )
  assert.ok(patch)
  assert.deepEqual(requestBody(patch), {
    address: '99 New Street',
    preferred_language: 'ur',
  })
  assert.equal(
    (screen.getByLabelText('Service address') as HTMLTextAreaElement).value,
    '99 New Street',
  )
})

test('profile page displays API validation errors', async () => {
  const client = createTestClient((request) => {
    if (method(request) === 'PATCH') {
      return errorResponse(
        422,
        'validation_error',
        'Request validation failed.',
        [
          {
            loc: ['body', 'preferred_language'],
            msg: 'String should have at least 2 characters',
            type: 'string_too_short',
          },
        ],
      )
    }
    return jsonResponse(profile())
  })

  renderRoute(client, <CustomerProfilePage />, {
    initialEntry: '/customer/profile',
    path: '/customer/profile',
  })

  assert.ok(await screen.findByText('Ayesha Khan'))
  fireEvent.change(screen.getByLabelText('Preferred language'), {
    target: { value: 'en' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Save profile' }))

  assert.ok(
    await screen.findByText('String should have at least 2 characters'),
  )
  assert.ok(screen.getByText('Please correct the highlighted fields.'))
})

test('equipment list handles loading, empty, and API failure states', async () => {
  const loadedClient = createTestClient(() =>
    jsonResponse(page([equipment()])),
  )

  const loaded = renderRoute(loadedClient, <EquipmentListPage />, {
    initialEntry: '/customer/equipment',
    path: '/customer/equipment',
  })

  assert.ok(await screen.findByText('Acme Sun 500'))
  assert.ok(screen.getByText('1 equipment record'))
  loaded.unmount()

  const emptyClient = createTestClient(() => jsonResponse(page([])))
  renderRoute(emptyClient, <EquipmentListPage />, {
    initialEntry: '/customer/equipment',
    path: '/customer/equipment',
  })
  assert.ok(await screen.findByText('No equipment registered'))

  cleanup()

  const failedClient = createTestClient(() =>
    errorResponse(500, 'internal_error', 'Equipment service unavailable.'),
  )
  renderRoute(failedClient, <EquipmentListPage />, {
    initialEntry: '/customer/equipment',
    path: '/customer/equipment',
  })
  assert.ok(await screen.findByText('Something went wrong'))
  assert.ok(screen.getByText('Equipment service unavailable.'))
})

test('equipment create, edit, and delete use the customer endpoints', async () => {
  const createRequests: RecordedRequest[] = []
  const createClient = createTestClient(
    (request) =>
      method(request) === 'POST'
        ? jsonResponse(equipment({ model: 'Sun 700' }), 201)
        : errorResponse(404, 'not_found', 'Unexpected request'),
    createRequests,
  )

  renderRoute(createClient, <EquipmentNewPage />, {
    initialEntry: '/customer/equipment/new',
    path: '/customer/equipment/new',
  })

  fireEvent.change(screen.getByLabelText(/Manufacturer/), {
    target: { value: 'Acme' },
  })
  fireEvent.change(screen.getByLabelText(/Model/), {
    target: { value: 'Sun 700' },
  })
  fireEvent.change(screen.getByLabelText(/Equipment type/), {
    target: { value: 'solar_inverter' },
  })
  fireEvent.change(screen.getByLabelText('Serial number'), {
    target: { value: 'SN-700' },
  })
  fireEvent.change(screen.getByLabelText('Installation date'), {
    target: { value: '2024-06-01' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Register equipment' }))

  await waitFor(() => {
    assert.equal(
      screen.getByTestId('location').textContent,
      '/customer/equipment/equipment-1',
    )
  })
  const create = requestsTo(
    createRequests,
    '/api/v1/customers/me/equipment',
  ).find((request) => method(request) === 'POST')
  assert.ok(create)
  assert.deepEqual(requestBody(create), {
    manufacturer: 'Acme',
    model: 'Sun 700',
    serial_number: 'SN-700',
    equipment_type: 'solar_inverter',
    installation_date: '2024-06-01',
  })

  cleanup()

  const editRequests: RecordedRequest[] = []
  const editClient = createTestClient((request) => {
    if (method(request) === 'PATCH') {
      return jsonResponse(equipment({ model: 'Sun 800' }))
    }
    return jsonResponse(equipment())
  }, editRequests)

  renderRoute(editClient, <EquipmentEditPage />, {
    initialEntry: '/customer/equipment/equipment-1/edit',
    path: '/customer/equipment/:equipmentId/edit',
  })

  const model = await screen.findByLabelText(/Model/)
  fireEvent.change(model, { target: { value: 'Sun 800' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

  await waitFor(() => {
    assert.equal(
      screen.getByTestId('location').textContent,
      '/customer/equipment/equipment-1',
    )
  })
  const patch = requestsTo(
    editRequests,
    '/api/v1/customers/me/equipment/equipment-1',
  ).find((request) => method(request) === 'PATCH')
  assert.ok(patch)
  assert.deepEqual(requestBody(patch), {
    manufacturer: 'Acme',
    model: 'Sun 800',
    serial_number: 'SN-1',
    equipment_type: 'solar_inverter',
    installation_date: '2024-05-01',
  })

  cleanup()

  const deleteRequests: RecordedRequest[] = []
  const deleteClient = createTestClient(
    (request) =>
      method(request) === 'DELETE'
        ? emptyResponse()
        : jsonResponse(equipment()),
    deleteRequests,
  )
  window.confirm = () => true

  renderRoute(deleteClient, <EquipmentDetailPage />, {
    initialEntry: '/customer/equipment/equipment-1',
    path: '/customer/equipment/:equipmentId',
  })

  assert.ok(await screen.findByText('Acme Sun 500'))
  fireEvent.click(screen.getByRole('button', { name: 'Delete equipment' }))

  await waitFor(() => {
    assert.equal(
      screen.getByTestId('location').textContent,
      '/customer/equipment',
    )
  })
  assert.equal(
    requestsTo(deleteRequests, '/api/v1/customers/me/equipment/equipment-1')
      .filter((request) => method(request) === 'DELETE').length,
    1,
  )
})

test('equipment delete explains the 409 equipment_in_use response', async () => {
  const client = createTestClient((request) =>
    method(request) === 'DELETE'
      ? errorResponse(
          409,
          'equipment_in_use',
          'Equipment has historical records and cannot be deleted.',
        )
      : jsonResponse(equipment()),
  )
  window.confirm = () => true

  renderRoute(client, <EquipmentDetailPage />, {
    initialEntry: '/customer/equipment/equipment-1',
    path: '/customer/equipment/:equipmentId',
  })

  assert.ok(await screen.findByText('Acme Sun 500'))
  fireEvent.click(screen.getByRole('button', { name: 'Delete equipment' }))

  assert.ok(
    await screen.findByText(/referenced by an existing complaint/),
  )
})

test('complaint list loads and applies supported filters', async () => {
  const requests: RecordedRequest[] = []
  const client = createTestClient((request) => {
    if (request.url.pathname === '/api/v1/customers/me/equipment') {
      return jsonResponse(page([equipment()]))
    }
    if (request.url.pathname === '/api/v1/customers/me/complaints') {
      return jsonResponse(page([complaint()]))
    }
    return errorResponse(404, 'not_found', 'Unexpected request')
  }, requests)

  renderRoute(client, <ComplaintListPage />, {
    initialEntry: '/customer/complaints',
    path: '/customer/complaints',
  })

  assert.ok(
    await screen.findByText(
      'The inverter stopped producing power after sunrise.',
    ),
  )

  fireEvent.change(screen.getByLabelText('Status'), {
    target: { value: 'received' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Apply filters' }))

  await waitFor(() => {
    const filtered = requests.filter(
      (request) =>
        request.url.pathname === '/api/v1/customers/me/complaints' &&
        request.url.searchParams.get('status') === 'received',
    )
    assert.equal(filtered.length, 1)
  })
})

test('complaint submission validates input and never starts diagnostics', async () => {
  const requests: RecordedRequest[] = []
  const client = createTestClient((request) => {
    if (request.url.pathname === '/api/v1/customers/me/equipment') {
      return jsonResponse(page([equipment()]))
    }
    if (
      request.url.pathname === '/api/v1/customers/me/complaints' &&
      method(request) === 'POST'
    ) {
      return jsonResponse(complaint(), 201)
    }
    return errorResponse(404, 'not_found', 'Unexpected request')
  }, requests)

  renderRoute(client, <ComplaintNewPage />, {
    initialEntry: '/customer/complaints/new',
    path: '/customer/complaints/new',
  })

  assert.ok(
    await screen.findByRole('option', {
      name: 'Acme Sun 500 (solar_inverter)',
    }),
  )

  fireEvent.click(screen.getByRole('button', { name: 'Submit complaint' }))
  assert.ok(
    await screen.findByText('Describe the problem before submitting.'),
  )
  assert.equal(
    requests.filter((request) => method(request) === 'POST').length,
    0,
  )

  fireEvent.change(screen.getByLabelText(/Describe the problem/), {
    target: {
      value: '  The inverter stopped producing power after sunrise.  ',
    },
  })
  fireEvent.change(screen.getByLabelText('Equipment'), {
    target: { value: 'equipment-1' },
  })
  fireEvent.change(screen.getByLabelText('Error code'), {
    target: { value: '  E-05  ' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Submit complaint' }))

  await waitFor(() => {
    assert.equal(
      screen.getByTestId('location').textContent,
      '/customer/complaints/complaint-1',
    )
  })

  const create = requests.find(
    (request) =>
      request.url.pathname === '/api/v1/customers/me/complaints' &&
      method(request) === 'POST',
  )
  assert.ok(create)
  assert.deepEqual(requestBody(create), {
    description: 'The inverter stopped producing power after sunrise.',
    equipment_id: 'equipment-1',
    reported_error_code: 'E-05',
  })
  assert.equal(
    requests.some((request) =>
      request.url.pathname.includes('/diagnostics/investigate'),
    ),
    false,
  )
})

test('complaint submission prevents duplicate requests', async () => {
  const requests: RecordedRequest[] = []
  let resolveSubmission: (response: Response) => void = () => undefined
  const pending = new Promise<Response>((resolve) => {
    resolveSubmission = resolve
  })

  const client = createTestClient((request) => {
    if (request.url.pathname === '/api/v1/customers/me/equipment') {
      return jsonResponse(page([equipment()]), 200)
    }
    if (
      request.url.pathname === '/api/v1/customers/me/complaints' &&
      method(request) === 'POST'
    ) {
      return pending
    }
    return errorResponse(404, 'not_found', 'Unexpected request')
  }, requests)

  renderRoute(client, <ComplaintNewPage />, {
    initialEntry: '/customer/complaints/new',
    path: '/customer/complaints/new',
  })

  assert.ok(
    await screen.findByRole('option', {
      name: 'Acme Sun 500 (solar_inverter)',
    }),
  )
  fireEvent.change(screen.getByLabelText(/Describe the problem/), {
    target: { value: 'The inverter stopped producing power.' },
  })

  const form = formFor('Submit complaint')
  fireEvent.submit(form)
  fireEvent.submit(form)

  await waitFor(() => {
    assert.equal(
      requests.filter((request) => method(request) === 'POST').length,
      1,
    )
  })

  resolveSubmission(jsonResponse(complaint(), 201))
  await waitFor(() => {
    assert.equal(
      screen.getByTestId('location').textContent,
      '/customer/complaints/complaint-1',
    )
  })
})

test('complaint detail loads directly without the complaint list', async () => {
  const requests: RecordedRequest[] = []
  const olderComplaint = complaint({
    id: 'older-complaint-99',
    description: 'An older complaint outside the first page of results.',
  })

  const client = createTestClient((request) => {
    if (
      request.url.pathname ===
      '/api/v1/customers/me/complaints/older-complaint-99'
    ) {
      return jsonResponse(olderComplaint)
    }
    return errorResponse(404, 'not_found', 'Unexpected request')
  }, requests)

  renderRoute(client, <ComplaintDetailPage />, {
    initialEntry: '/customer/complaints/older-complaint-99',
    path: '/customer/complaints/:complaintId',
  })

  assert.ok(
    await screen.findByText(
      'An older complaint outside the first page of results.',
    ),
  )
  assert.equal(
    requests.some(
      (request) =>
        request.url.pathname === '/api/v1/customers/me/complaints',
    ),
    false,
  )
})

test('complaint detail shows a safe error for missing or inaccessible records', async () => {
  const client = createTestClient(() =>
    errorResponse(404, 'not_found', 'Complaint not found'),
  )

  renderRoute(client, <ComplaintDetailPage />, {
    initialEntry: '/customer/complaints/missing-complaint',
    path: '/customer/complaints/:complaintId',
  })

  assert.ok(
    await screen.findByText(
      'This complaint could not be found or is not available to your account.',
    ),
  )
  assert.ok(screen.queryByText('Complaint not found') === null)
})

test('dashboard distinguishes loaded complaint counts from API totals', async () => {
  const equipmentItems = Array.from({ length: 100 }, (_, index) =>
    equipment({ id: `equipment-${index}` }),
  )
  const complaintItems = Array.from({ length: 100 }, (_, index) =>
    complaint({
      id: `complaint-${index}`,
      status: index < 20 ? 'awaiting_customer' : 'received',
    }),
  )

  const client = createTestClient((request) => {
    if (request.url.pathname === '/api/v1/customers/me') {
      return jsonResponse(profile())
    }
    if (request.url.pathname === '/api/v1/customers/me/equipment') {
      return jsonResponse(page(equipmentItems, 250))
    }
    if (request.url.pathname === '/api/v1/customers/me/complaints') {
      return jsonResponse(page(complaintItems, 300))
    }
    return errorResponse(404, 'not_found', 'Unexpected request')
  })

  renderRoute(client, <CustomerDashboardPage />, {
    initialEntry: '/customer',
    path: '/customer',
  })

  assert.ok(await screen.findByText('Welcome, Ayesha Khan'))
  assert.ok(
    within(summaryCard('Registered equipment')).getByText('250'),
  )
  assert.ok(
    within(summaryCard('Complaints submitted')).getByText('300'),
  )
  assert.ok(
    within(summaryCard('Awaiting your response')).getByText('20'),
  )
  assert.ok(
    screen.getByText(
      'Total reported by the API. 100 of 250 equipment records loaded in this view.',
    ),
  )
  assert.ok(
    screen.getByText(
      'Total reported by the API. 100 of 300 complaints loaded in this view.',
    ),
  )
  assert.ok(
    screen.getByText(
      'Based on the 100 complaints loaded in this view (of 300 total).',
    ),
  )
  assert.ok(
    screen.getByText(
      'Status breakdown is based on the 100 complaints loaded in this view (of 300 total).',
    ),
  )
})

test('dashboard handles empty and failed requests', async () => {
  const emptyClient = createTestClient((request) => {
    if (request.url.pathname === '/api/v1/customers/me') {
      return jsonResponse(profile())
    }
    return jsonResponse(page([]))
  })

  renderRoute(emptyClient, <CustomerDashboardPage />, {
    initialEntry: '/customer',
    path: '/customer',
  })

  assert.ok(await screen.findByText('No equipment registered'))
  assert.ok(screen.getByText('No complaints yet'))
  assert.equal(
    within(summaryCard('Registered equipment')).queryByText('0')?.textContent,
    '0',
  )

  cleanup()

  const failedClient = createTestClient((request) => {
    if (request.url.pathname === '/api/v1/customers/me') {
      return jsonResponse(profile())
    }
    if (request.url.pathname === '/api/v1/customers/me/equipment') {
      return errorResponse(500, 'internal_error', 'Dashboard unavailable.')
    }
    return jsonResponse(page([complaint()]))
  })

  renderRoute(failedClient, <CustomerDashboardPage />, {
    initialEntry: '/customer',
    path: '/customer',
  })

  assert.ok(await screen.findByText('Something went wrong'))
  assert.ok(screen.getByText('Dashboard unavailable.'))
})
