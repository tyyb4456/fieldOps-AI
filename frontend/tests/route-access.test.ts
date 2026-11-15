import assert from 'node:assert/strict'
import test from 'node:test'
import type { CurrentUser } from '../src/features/accounts/types.ts'
import { resolveRouteAccess } from '../src/auth/route-access.ts'

function user(role: CurrentUser['role'], isActive = true): CurrentUser {
  return {
    id: 'user-1',
    full_name: 'Test User',
    email: null,
    phone: null,
    role,
    is_active: isActive,
    customer_id: role === 'customer' ? 'customer-1' : null,
    technician_id: role === 'technician' ? 'technician-1' : null,
  }
}

function signedOut() {
  return {
    user: null,
    isLoading: false,
    isUnauthorized: false,
    error: null,
  }
}

test('authentication loading state blocks route rendering', () => {
  assert.deepEqual(
    resolveRouteAccess({ ...signedOut(), isLoading: true }),
    { kind: 'loading' },
  )
})

test('profile loading errors render an error state', () => {
  assert.deepEqual(
    resolveRouteAccess({ ...signedOut(), error: 'Account unavailable' }),
    { kind: 'error', message: 'Account unavailable' },
  )
})

test('unauthenticated users are redirected to sign in with return path', () => {
  assert.deepEqual(
    resolveRouteAccess(signedOut(), { currentPath: '/admin' }),
    {
      kind: 'redirect',
      to: '/sign-in',
      state: { from: '/admin' },
    },
  )
})

test('403 authorization failures redirect to the unauthorized page', () => {
  assert.deepEqual(
    resolveRouteAccess({ ...signedOut(), isUnauthorized: true }),
    { kind: 'redirect', to: '/unauthorized' },
  )
})

test('inactive accounts are denied', () => {
  assert.deepEqual(
    resolveRouteAccess({
      ...signedOut(),
      user: user('customer', false),
    }),
    { kind: 'redirect', to: '/unauthorized' },
  )
})

test('unknown roles are denied', () => {
  assert.deepEqual(
    resolveRouteAccess({
      ...signedOut(),
      user: { ...user('customer'), role: 'owner' as CurrentUser['role'] },
    }),
    { kind: 'redirect', to: '/unauthorized' },
  )
})

test('role restrictions deny cross-role access', () => {
  assert.deepEqual(
    resolveRouteAccess(
      { ...signedOut(), user: user('technician') },
      { allowedRoles: ['admin'] },
    ),
    { kind: 'redirect', to: '/unauthorized' },
  )
})

test('allowed roles render the protected route', () => {
  assert.deepEqual(
    resolveRouteAccess(
      { ...signedOut(), user: user('admin') },
      { allowedRoles: ['admin'] },
    ),
    { kind: 'allow' },
  )
})

test('customer and admin accounts cannot access technician screens', () => {
  for (const role of ['customer', 'admin'] as const) {
    assert.deepEqual(
      resolveRouteAccess(
        { ...signedOut(), user: user(role) },
        { allowedRoles: ['technician'] },
      ),
      { kind: 'redirect', to: '/unauthorized' },
    )
  }
})

test('technicians are allowed on technician-only screens', () => {
  assert.deepEqual(
    resolveRouteAccess(
      { ...signedOut(), user: user('technician') },
      { allowedRoles: ['technician'] },
    ),
    { kind: 'allow' },
  )
})

test('every supported role is allowed on its own workspace', () => {
  for (const role of ['customer', 'technician', 'admin'] as const) {
    assert.deepEqual(
      resolveRouteAccess(
        { ...signedOut(), user: user(role) },
        { allowedRoles: [role] },
      ),
      { kind: 'allow' },
    )
  }
})
