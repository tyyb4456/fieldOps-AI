import { SignUp, useAuth } from '@clerk/react'
import { Navigate } from 'react-router-dom'
import { LoadingScreen } from '../components/LoadingScreen'

export function SignUpPage() {
  const { isLoaded, isSignedIn } = useAuth()

  if (!isLoaded) {
    return <LoadingScreen label="Loading sign up…" />
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
            Create your account
          </h1>
          <p className="mt-2 text-sm text-slate-400">
            New accounts start with customer access. Technician and
            administrator access is provisioned separately by an operator.
          </p>
        </div>
        <SignUp
          routing="path"
          path="/sign-up"
          signInUrl="/sign-in"
          fallbackRedirectUrl="/dashboard"
        />
      </div>
    </div>
  )
}
