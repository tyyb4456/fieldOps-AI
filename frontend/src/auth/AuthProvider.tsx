import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { useAuth } from '@clerk/react'
import { ApiError, fetchCurrentUser, type CurrentUser } from '../lib/api'
import { AppAuthContext, type AppAuthState } from './app-auth-context'

export function AppAuthProvider({ children }: { children: ReactNode }) {
  const { isLoaded, isSignedIn, getToken, signOut } = useAuth()
  const [user, setUser] = useState<CurrentUser | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  const refresh = useCallback(() => {
    setReloadKey((key) => key + 1)
  }, [])

  useEffect(() => {
    let cancelled = false

    async function load() {
      if (!isLoaded) {
        return
      }

      if (!isSignedIn) {
        setUser(null)
        setError(null)
        setIsLoading(false)
        return
      }

      setIsLoading(true)
      setError(null)

      try {
        const token = await getToken()
        if (!token) {
          throw new ApiError(
            401,
            'missing_token',
            'Unable to obtain a Clerk session token.',
          )
        }

        const currentUser = await fetchCurrentUser(token)
        if (!cancelled) {
          setUser(currentUser)
        }
      } catch (caught) {
        if (cancelled) {
          return
        }

        if (caught instanceof ApiError && caught.status === 401) {
          await signOut()
          return
        }

        setError(
          caught instanceof Error
            ? caught.message
            : 'Unable to load your FieldOps account.',
        )
      } finally {
        if (!cancelled) {
          setIsLoading(false)
        }
      }
    }

    void load()

    return () => {
      cancelled = true
    }
  }, [getToken, isLoaded, isSignedIn, reloadKey, signOut])

  const value = useMemo<AppAuthState>(
    () => ({ user, isLoading, error, refresh }),
    [error, isLoading, refresh, user],
  )

  return (
    <AppAuthContext.Provider value={value}>
      {children}
    </AppAuthContext.Provider>
  )
}
