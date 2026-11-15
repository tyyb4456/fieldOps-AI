import type { UserRole } from '../lib/api/types.ts'
import { isUserRole } from '../lib/api/types.ts'
import type { CurrentUser } from '../features/accounts/types.ts'

export interface RouteAuthState {
  user: CurrentUser | null
  isLoading: boolean
  isUnauthorized: boolean
  error: string | null
}

export type RouteAccess =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | {
      kind: 'redirect'
      to: '/sign-in' | '/unauthorized'
      state?: { from: string }
    }
  | { kind: 'allow' }

export function resolveRouteAccess(
  auth: RouteAuthState,
  options: {
    allowedRoles?: UserRole[]
    currentPath?: string
  } = {},
): RouteAccess {
  const { allowedRoles, currentPath } = options

  if (auth.isLoading) {
    return { kind: 'loading' }
  }

  if (auth.error !== null) {
    return { kind: 'error', message: auth.error }
  }

  if (auth.isUnauthorized) {
    return { kind: 'redirect', to: '/unauthorized' }
  }

  if (auth.user === null) {
    return {
      kind: 'redirect',
      to: '/sign-in',
      state: currentPath ? { from: currentPath } : undefined,
    }
  }

  if (!isUserRole(auth.user.role) || !auth.user.is_active) {
    return { kind: 'redirect', to: '/unauthorized' }
  }

  if (allowedRoles && !allowedRoles.includes(auth.user.role)) {
    return { kind: 'redirect', to: '/unauthorized' }
  }

  return { kind: 'allow' }
}
