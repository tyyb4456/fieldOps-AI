import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { useAuth } from '@clerk/react'
import {
  ApiError,
  bootstrapCurrentUser,
  fetchCurrentUser,
  type CurrentUser,
} from '../lib/api'
import { classifyAuthError } from './auth-errors'
import { AppAuthContext, type AppAuthState } from './app-auth-context'

export function AppAuthProvider({ children }: { children: ReactNode }) {
  const { isLoaded, isSignedIn, getToken, signOut } = useAuth()
  const [user, setUser] = useState<CurrentUser | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isUnauthorized, setIsUnauthorized] = useState(false)
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
        setIsUnauthorized(false)
        setIsLoading(false)
        return
      }

      setIsLoading(true)
      setIsUnauthorized(false)
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

        let currentUser: CurrentUser
        try {
          currentUser = await fetchCurrentUser(token)
        } catch (caught) {
          const failure = classifyAuthError(caught)
          if (failure.kind !== 'not-provisioned') {
            throw caught
          }
          currentUser = await bootstrapCurrentUser(token)
        }

        if (!cancelled) {
          setUser(currentUser)
        }
      } catch (caught) {
        if (cancelled) {
          return
        }

        const failure = classifyAuthError(caught)

        if (failure.kind === 'sign-out') {
          setUser(null)
          await signOut()
          return
        }

        if (failure.kind === 'unauthorized') {
          setUser(null)
          setIsUnauthorized(true)
          return
        }

        setError(
          failure.kind === 'error'
            ? failure.message
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
    () => ({ user, isLoading, isUnauthorized, error, refresh }),
    [error, isLoading, isUnauthorized, refresh, user],
  )

  return (
    <AppAuthContext.Provider value={value}>
      {children}
    </AppAuthContext.Provider>
  )
}
