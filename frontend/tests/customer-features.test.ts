import assert from 'node:assert/strict'
import test from 'node:test'
import { validateCustomerProfileForm } from '../src/features/customers/validation.ts'
import {
  complaintStatusCounts,
  summarizeCustomerDashboard,
} from '../src/features/customers/dashboard.ts'
import type { Complaint } from '../src/features/complaints/types.ts'
import type { Equipment } from '../src/features/equipment/types.ts'
import { validateComplaintForm } from '../src/features/complaints/validation.ts'
import { validateEquipmentForm } from '../src/features/equipment/validation.ts'

test('customer profile validation trims values and clears empty fields', () => {
  const result = validateCustomerProfileForm({
    address: '  12 Solar Street  ',
    preferredLanguage: '  ',
  })

  assert.deepEqual(result, {
    isValid: true,
    errors: {},
    payload: {
      address: '12 Solar Street',
      preferred_language: null,
    },
  })
})

test('customer profile validation enforces language and address bounds', () => {
  const shortLanguage = validateCustomerProfileForm({
    address: '',
    preferredLanguage: 'e',
  })
  assert.equal(shortLanguage.isValid, false)
  assert.match(shortLanguage.errors.preferredLanguage ?? '', /at least 2/)

  const longAddress = validateCustomerProfileForm({
    address: 'a'.repeat(2001),
    preferredLanguage: 'en',
  })
  assert.equal(longAddress.isValid, false)
  assert.match(longAddress.errors.address ?? '', /2000 characters or fewer/)
})

test('equipment validation trims fields and normalizes optional values', () => {
  const result = validateEquipmentForm(
    {
      manufacturer: '  Acme  ',
      model: '  Inverter X  ',
      serialNumber: '   ',
      equipmentType: ' solar_inverter ',
      installationDate: '2026-01-15',
    },
    new Date(2026, 10, 15),
  )

  assert.deepEqual(result, {
    isValid: true,
    errors: {},
    payload: {
      manufacturer: 'Acme',
      model: 'Inverter X',
      serial_number: null,
      equipment_type: 'solar_inverter',
      installation_date: '2026-01-15',
    },
  })
})

test('equipment validation rejects future and invalid installation dates', () => {
  const base = {
    manufacturer: 'Acme',
    model: 'Inverter X',
    serialNumber: '',
    equipmentType: 'solar_inverter',
    installationDate: '2026-11-16',
  }

  const future = validateEquipmentForm(base, new Date(2026, 10, 15))
  assert.equal(future.isValid, false)
  assert.match(future.errors.installationDate ?? '', /future/)

  const invalid = validateEquipmentForm(
    { ...base, installationDate: '2026-02-30' },
    new Date(2026, 10, 15),
  )
  assert.equal(invalid.isValid, false)
  assert.match(invalid.errors.installationDate ?? '', /valid installation date/)
})

test('complaint validation requires a description and known equipment', () => {
  const empty = validateComplaintForm(
    { description: '   ', equipmentId: '', errorCode: '' },
    [],
  )
  assert.equal(empty.isValid, false)
  assert.match(empty.errors.description ?? '', /Describe the problem/)

  const short = validateComplaintForm(
    { description: 'abcd', equipmentId: '', errorCode: '' },
    [],
  )
  assert.equal(short.isValid, false)
  assert.match(short.errors.description ?? '', /at least 5/)

  const unknownEquipment = validateComplaintForm(
    { description: 'Inverter is offline', equipmentId: 'other', errorCode: '' },
    ['equipment-1'],
  )
  assert.equal(unknownEquipment.isValid, false)
  assert.match(unknownEquipment.errors.equipmentId ?? '', /registered equipment/)
})

test('complaint validation builds a complaint payload with optional fields', () => {
  const result = validateComplaintForm(
    {
      description: '  Inverter is offline  ',
      equipmentId: 'equipment-1',
      errorCode: '  E042  ',
    },
    ['equipment-1'],
  )

  assert.deepEqual(result, {
    isValid: true,
    errors: {},
    payload: {
      description: 'Inverter is offline',
      equipment_id: 'equipment-1',
      reported_error_code: 'E042',
    },
  })
})

function complaint(status: Complaint['status']): Complaint {
  return {
    id: `complaint-${status}`,
    customer_id: 'customer-1',
    equipment_id: null,
    description: 'Test complaint',
    reported_symptoms: [],
    reported_error_code: null,
    channel: 'web',
    status,
    priority: 'normal',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  }
}

test('complaint status counts summarize only loaded complaints', () => {
  const complaints = [
    complaint('received'),
    complaint('received'),
    complaint('awaiting_customer'),
    complaint('closed'),
  ]

  assert.deepEqual(complaintStatusCounts(complaints), {
    received: 2,
    awaiting_customer: 1,
    closed: 1,
  })
})

function equipment(id: string): Equipment {
  return {
    id,
    customer_id: 'customer-1',
    manufacturer: 'Acme',
    model: 'Sun 500',
    serial_number: null,
    equipment_type: 'solar_inverter',
    installation_date: null,
    created_at: '2026-01-01T00:00:00Z',
  }
}

test('dashboard summary uses API totals and only labels loaded counts when truncated', () => {
  const summary = summarizeCustomerDashboard(
    { items: [equipment('equipment-1')], total: 1, limit: 100, offset: 0 },
    {
      items: [complaint('received'), complaint('awaiting_customer')],
      total: 2,
      limit: 100,
      offset: 0,
    },
  )

  assert.equal(summary.equipmentTotal, 1)
  assert.equal(summary.equipmentLoaded, 1)
  assert.equal(summary.equipmentNote, null)
  assert.equal(summary.complaintTotal, 2)
  assert.equal(summary.complaintLoaded, 2)
  assert.equal(summary.complaintNote, null)
  assert.equal(summary.awaitingResponse, 1)
  assert.equal(summary.awaitingResponseNote, null)
  assert.equal(summary.statusBreakdownNote, null)
  assert.deepEqual(summary.visibleStatuses, ['received', 'awaiting_customer'])
})

test('dashboard summary labels truncated loaded counts separately from API totals', () => {
  const summary = summarizeCustomerDashboard(
    {
      items: [equipment('equipment-1')],
      total: 250,
      limit: 100,
      offset: 0,
    },
    {
      items: [complaint('awaiting_customer'), complaint('received')],
      total: 300,
      limit: 100,
      offset: 0,
    },
  )

  assert.equal(summary.equipmentTotal, 250)
  assert.equal(summary.equipmentLoaded, 1)
  assert.match(
    summary.equipmentNote ?? '',
    /Total reported by the API\. 1 of 250 equipment records loaded/,
  )
  assert.equal(summary.complaintTotal, 300)
  assert.equal(summary.complaintLoaded, 2)
  assert.match(
    summary.complaintNote ?? '',
    /Total reported by the API\. 2 of 300 complaints loaded/,
  )
  assert.match(
    summary.awaitingResponseNote ?? '',
    /Based on the 2 complaints loaded in this view \(of 300 total\)/,
  )
  assert.match(
    summary.statusBreakdownNote ?? '',
    /Status breakdown is based on the 2 complaints loaded in this view/,
  )
})

test('dashboard summary treats pages beyond offset zero as truncated', () => {
  const summary = summarizeCustomerDashboard(
    { items: [equipment('equipment-101')], total: 250, limit: 100, offset: 100 },
    { items: [complaint('received')], total: 300, limit: 100, offset: 100 },
  )

  assert.match(summary.equipmentNote ?? '', /1 of 250 equipment records loaded/)
  assert.match(summary.complaintNote ?? '', /1 of 300 complaints loaded/)
})
