import { createContext, useContext } from 'react'
import type { CurrentUser } from '../lib/api'

export interface AppAuthState {
  user: CurrentUser | null
  isLoading: boolean
  error: string | null
  refresh: () => void
}

export const AppAuthContext = createContext<AppAuthState | undefined>(
  undefined,
)

export function useAppAuth(): AppAuthState {
  const context = useContext(AppAuthContext)
  if (context === undefined) {
    throw new Error('useAppAuth must be used within AppAuthProvider')
  }
  return context
}
