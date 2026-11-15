import { useAuth } from '@clerk/react'
import { useMemo, type ReactNode } from 'react'
import { ApiClient } from './client'
import { configuredApiBaseUrl } from './config'
import { ApiClientContext } from './api-client-context'

export function ApiClientProvider({ children }: { children: ReactNode }) {
  const { getToken } = useAuth()
  const client = useMemo(
    () =>
      new ApiClient({
        baseUrl: configuredApiBaseUrl(),
        getToken: () => getToken(),
      }),
    [getToken],
  )

  return (
    <ApiClientContext.Provider value={client}>
      {children}
    </ApiClientContext.Provider>
  )
}
