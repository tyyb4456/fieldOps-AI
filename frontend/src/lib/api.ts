import { ApiError } from './api-error'
import { resolveApiBaseUrl } from './api-url'

export { ApiError } from './api-error'

export type UserRole = 'customer' | 'technician' | 'admin'

export interface CurrentUser {
  id: string
  full_name: string
  email: string | null
  phone: string | null
  role: UserRole
  is_active: boolean
  customer_id: string | null
  technician_id: string | null
}

interface ApiErrorPayload {
  error?: {
    code?: string
    message?: string
  }
}

const API_BASE_URL = resolveApiBaseUrl(
  import.meta.env.VITE_API_BASE_URL,
  { isProduction: import.meta.env.PROD },
)

async function requestCurrentUser(
  path: string,
  method: 'GET' | 'POST',
  token: string,
): Promise<CurrentUser> {
  let response: Response

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/json',
      },
    })
  } catch {
    throw new ApiError(
      0,
      'network_error',
      'Unable to reach the FieldOps API. Check your connection and try again.',
    )
  }

  if (!response.ok) {
    let payload: ApiErrorPayload | null = null
    try {
      payload = (await response.json()) as ApiErrorPayload
    } catch {
      payload = null
    }

    throw new ApiError(
      response.status,
      payload?.error?.code ?? 'request_failed',
      payload?.error?.message ?? 'The API rejected this request.',
    )
  }

  return (await response.json()) as CurrentUser
}

export async function fetchCurrentUser(token: string): Promise<CurrentUser> {
  return requestCurrentUser('/api/v1/users/me', 'GET', token)
}

export async function bootstrapCurrentUser(
  token: string,
): Promise<CurrentUser> {
  return requestCurrentUser('/api/v1/auth/bootstrap', 'POST', token)
}
