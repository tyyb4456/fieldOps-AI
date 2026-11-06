export type AuthFailure =
  | { kind: 'sign-out' }
  | { kind: 'not-provisioned' }
  | { kind: 'unauthorized'; message: string }
  | { kind: 'error'; message: string }

interface ApiErrorLike {
  status: number
  code: string
  message: string
}

function isApiErrorLike(error: unknown): error is ApiErrorLike {
  if (typeof error !== 'object' || error === null) {
    return false
  }
  const candidate = error as Partial<ApiErrorLike>
  return (
    typeof candidate.status === 'number' &&
    typeof candidate.code === 'string' &&
    typeof candidate.message === 'string'
  )
}

export function classifyAuthError(error: unknown): AuthFailure {
  if (isApiErrorLike(error)) {
    if (error.status === 401) {
      return { kind: 'sign-out' }
    }
    if (
      error.status === 404 &&
      error.code === 'account_not_provisioned'
    ) {
      return { kind: 'not-provisioned' }
    }
    if (error.status === 403) {
      return { kind: 'unauthorized', message: error.message }
    }
    return { kind: 'error', message: error.message }
  }

  return {
    kind: 'error',
    message:
      error instanceof Error
        ? error.message
        : 'Unable to load your FieldOps account.',
  }
}
