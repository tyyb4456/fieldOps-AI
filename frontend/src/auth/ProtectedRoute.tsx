import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAppAuth } from './app-auth-context'
import type { UserRole } from '../lib/api/types'
import { resolveRouteAccess } from './route-access'
import { ErrorScreen } from '../components/ErrorScreen'
import { LoadingScreen } from '../components/LoadingScreen'

interface ProtectedRouteProps {
  allowedRoles?: UserRole[]
  children: ReactNode
}

export function ProtectedRoute({
  allowedRoles,
  children,
}: ProtectedRouteProps) {
  const auth = useAppAuth()
  const location = useLocation()
  const access = resolveRouteAccess(auth, {
    allowedRoles,
    currentPath: location.pathname,
  })

  if (access.kind === 'loading') {
    return <LoadingScreen label="Checking your session..." />
  }

  if (access.kind === 'error') {
    return <ErrorScreen message={access.message} onRetry={auth.refresh} />
  }

  if (access.kind === 'redirect') {
    return (
      <Navigate
        to={access.to}
        replace
        state={access.state}
      />
    )
  }

  return <>{children}</>
}
