import { ClerkProvider } from '@clerk/react'
import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { ConfigError } from '../components/ConfigError'

const publishableKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY

export function ClerkRouterProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate()

  if (!publishableKey) {
    return <ConfigError />
  }

  return (
    <ClerkProvider
      publishableKey={publishableKey}
      routerPush={(to) => navigate(to)}
      routerReplace={(to) => navigate(to, { replace: true })}
      signInUrl="/sign-in"
      signUpUrl="/sign-up"
      afterSignOutUrl="/"
    >
      {children}
    </ClerkProvider>
  )
}
