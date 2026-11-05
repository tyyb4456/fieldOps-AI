import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAppAuth } from './app-auth-context'
import type { UserRole } from '../lib/api'
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
  const { user, isLoading, error, refresh } = useAppAuth()
  const location = useLocation()

  if (isLoading) {
    return <LoadingScreen label="Checking your session…" />
  }

  if (error) {
    return <ErrorScreen message={error} onRetry={refresh} />
  }

  if (!user) {
    return (
      <Navigate
        to="/sign-in"
        replace
        state={{ from: location.pathname }}
      />
    )
  }

  if (!user.is_active) {
    return <Navigate to="/unauthorized" replace />
  }

  if (allowedRoles && !allowedRoles.includes(user.role)) {
    return <Navigate to="/unauthorized" replace />
  }

  return <>{children}</>
}
