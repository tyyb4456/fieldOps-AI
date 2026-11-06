import assert from 'node:assert/strict'
import test from 'node:test'
import { classifyAuthError } from '../src/auth/auth-errors.ts'

test('401 responses sign the user out', () => {
  assert.deepEqual(
    classifyAuthError({
      status: 401,
      code: 'unauthenticated',
      message: 'Invalid credentials',
    }),
    { kind: 'sign-out' },
  )
})

test('unprovisioned accounts trigger bootstrap', () => {
  assert.deepEqual(
    classifyAuthError({
      status: 404,
      code: 'account_not_provisioned',
      message: 'No account',
    }),
    { kind: 'not-provisioned' },
  )
})

test('403 responses are authorization failures, not sign-out', () => {
  assert.deepEqual(
    classifyAuthError({
      status: 403,
      code: 'account_inactive',
      message: 'This account is inactive.',
    }),
    {
      kind: 'unauthorized',
      message: 'This account is inactive.',
    },
  )
})

test('other API failures surface as errors', () => {
  assert.deepEqual(
    classifyAuthError({
      status: 500,
      code: 'internal_server_error',
      message: 'Unexpected error',
    }),
    { kind: 'error', message: 'Unexpected error' },
  )
})

test('network failures surface as errors', () => {
  assert.deepEqual(
    classifyAuthError(
      new Error('Unable to reach the FieldOps API.'),
    ),
    { kind: 'error', message: 'Unable to reach the FieldOps API.' },
  )
})

test('unknown values fall back to a generic message', () => {
  assert.deepEqual(classifyAuthError('unexpected'), {
    kind: 'error',
    message: 'Unable to load your FieldOps account.',
  })
})
