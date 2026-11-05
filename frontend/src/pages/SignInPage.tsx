import { SignIn, useAuth } from '@clerk/react'
import { Navigate } from 'react-router-dom'
import { LoadingScreen } from '../components/LoadingScreen'

export function SignInPage() {
  const { isLoaded, isSignedIn } = useAuth()

  if (!isLoaded) {
    return <LoadingScreen label="Loading sign in…" />
  }

  if (isSignedIn) {
    return <Navigate to="/dashboard" replace />
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 px-4 py-10">
      <div className="w-full max-w-md">
        <div className="mb-6 text-center">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-sky-400">
            FieldOps AI
          </p>
          <h1 className="mt-2 text-2xl font-semibold text-white">
            Sign in to your account
          </h1>
        </div>
        <SignIn
          routing="path"
          path="/sign-in"
          signUpUrl="/sign-up"
          fallbackRedirectUrl="/dashboard"
        />
      </div>
    </div>
  )
}
