import { ApiError } from '../../lib/api/errors.ts'
import { isUserRole } from '../../lib/api/types.ts'
import type { ApiClient } from '../../lib/api/client.ts'
import type { CurrentUser } from './types'

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function readNullableString(value: unknown, field: string): string | null {
  if (value === null || value === undefined) {
    return null
  }
  if (typeof value !== 'string') {
    throw new ApiError(
      500,
      'invalid_response',
      `The API returned an invalid "${field}" field.`,
    )
  }
  return value
}

export function parseCurrentUser(payload: unknown): CurrentUser {
  if (!isRecord(payload)) {
    throw new ApiError(
      500,
      'invalid_response',
      'The API returned an invalid account response.',
    )
  }

  const { id, full_name, email, phone, role, is_active, customer_id, technician_id } =
    payload

  if (typeof id !== 'string' || typeof full_name !== 'string') {
    throw new ApiError(
      500,
      'invalid_response',
      'The API returned an incomplete account response.',
    )
  }

  if (typeof is_active !== 'boolean') {
    throw new ApiError(
      500,
      'invalid_response',
      'The API returned an invalid "is_active" field.',
    )
  }

  if (!isUserRole(role)) {
    throw new ApiError(
      403,
      'unsupported_role',
      'Your account has a role this application does not support.',
    )
  }

  return {
    id,
    full_name,
    email: readNullableString(email, 'email'),
    phone: readNullableString(phone, 'phone'),
    role,
    is_active,
    customer_id: readNullableString(customer_id, 'customer_id'),
    technician_id: readNullableString(technician_id, 'technician_id'),
  }
}

export async function fetchCurrentUser(
  client: ApiClient,
): Promise<CurrentUser> {
  const payload = await client.get<unknown>('/api/v1/users/me')
  return parseCurrentUser(payload)
}

export async function bootstrapCurrentUser(
  client: ApiClient,
): Promise<CurrentUser> {
  const payload = await client.post<unknown>('/api/v1/auth/bootstrap')
  return parseCurrentUser(payload)
}
