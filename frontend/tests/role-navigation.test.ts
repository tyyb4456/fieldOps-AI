import assert from 'node:assert/strict'
import test from 'node:test'
import {
  ADMIN_NAV_ITEMS,
  TECHNICIAN_NAV_ITEMS,
  homePathForRole,
  navigationForRole,
  roleLabel,
} from '../src/navigation/role-navigation.ts'

test('customers see dashboard and customer navigation only', () => {
  assert.deepEqual(
    navigationForRole('customer').map((item) => item.to),
    ['/dashboard', '/customer'],
  )
})

test('technicians see dashboard and technician navigation only', () => {
  assert.deepEqual(
    navigationForRole('technician').map((item) => item.to),
    ['/dashboard', '/technician'],
  )
})

test('administrators see dashboard and administrator navigation only', () => {
  assert.deepEqual(
    navigationForRole('admin').map((item) => item.to),
    ['/dashboard', '/admin'],
  )
})

test('unknown or missing roles receive no navigation', () => {
  assert.deepEqual(navigationForRole('owner'), [])
  assert.deepEqual(navigationForRole(null), [])
  assert.equal(navigationForRole('owner').some((item) => item.to === '/admin'), false)
})

test('technician workspace navigation exposes the technician pages', () => {
  assert.deepEqual(
    TECHNICIAN_NAV_ITEMS.map((item) => item.to),
    [
      '/technician',
      '/technician/assignments',
      '/technician/work-orders',
      '/technician/service-records',
      '/technician/technical-references',
    ],
  )
})

test('administrator workspace navigation exposes the admin pages', () => {
  assert.deepEqual(
    ADMIN_NAV_ITEMS.map((item) => item.to),
    [
      '/admin',
      '/admin/complaints',
      '/admin/work-orders',
      '/admin/proposals',
      '/admin/assignments',
      '/admin/completion-reports',
      '/admin/documents',
      '/admin/technicians',
      '/admin/customers',
      '/admin/workflows',
    ],
  )
})

test('role home paths and labels come from one mapping', () => {
  assert.equal(homePathForRole('customer'), '/customer')
  assert.equal(homePathForRole('technician'), '/technician')
  assert.equal(homePathForRole('admin'), '/admin')
  assert.equal(homePathForRole('owner'), null)
  assert.equal(roleLabel('admin'), 'Administrator')
  assert.equal(roleLabel(undefined), null)
})
