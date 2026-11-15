import assert from 'node:assert/strict'
import test from 'node:test'
import { parseCurrentUser } from '../src/features/accounts/api.ts'
import { ApiError } from '../src/lib/api/errors.ts'

const validUser = {
  id: 'user-1',
  full_name: 'Test User',
  email: 'test@example.com',
  phone: null,
  role: 'customer',
  is_active: true,
  customer_id: 'customer-1',
  technician_id: null,
}

test('parses a valid current-user response', () => {
  assert.deepEqual(parseCurrentUser(validUser), validUser)
})

test('rejects an unsupported application role as authorization failure', () => {
  assert.throws(
    () => parseCurrentUser({ ...validUser, role: 'owner' }),
    (error: unknown) =>
      error instanceof ApiError &&
      error.status === 403 &&
      error.code === 'unsupported_role',
  )
})

test('rejects an incomplete account response', () => {
  assert.throws(
    () =>
      parseCurrentUser({
        ...validUser,
        full_name: undefined,
      }),
    (error: unknown) =>
      error instanceof ApiError &&
      error.status === 500 &&
      error.code === 'invalid_response',
  )
})

test('rejects non-object responses', () => {
  assert.throws(
    () => parseCurrentUser('not-an-object'),
    (error: unknown) =>
      error instanceof ApiError && error.code === 'invalid_response',
  )
})
